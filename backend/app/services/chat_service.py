import os
import re
import json
import math
import logging
import torch
import numpy as np
import ipaddress
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer, CrossEncoder
import faiss
from rank_bm25 import BM25Okapi
import fitz  # PyMuPDF

from .llm_gateway import llm_gateway
from ..core.config import RULES_PDF_PATH

logger = logging.getLogger("uvicorn.error")

# --- Models and Constants ---
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"

DENSE_TOP_K = 10
BM25_TOP_K = 10
RERANK_TOP_K = 12
FINAL_TOP_K = 5

CHUNK_SIZE_WORDS = 420
CHUNK_OVERLAP_WORDS = 70

class Component(BaseModel):
    id: str
    type: str
    interfaces: Optional[int] = None

class Edge(BaseModel):
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")

class Addressing(BaseModel):
    mode: Optional[str] = None
    cidrs: List[str] = []
    base_cidr: Optional[str] = None
    subnet_bindings: Dict = {}
    subnets: List[Dict] = []

class FirewallPolicy(BaseModel):
    mode: Optional[str] = None

class UserPolicies(BaseModel):
    allow_auto_addressing: bool = False

class Architecture(BaseModel):
    components: List[Component] = []
    edges: List[Edge] = []
    addressing: Addressing = Addressing()
    firewall_policy: FirewallPolicy = FirewallPolicy()
    user_policies: UserPolicies = UserPolicies()

class ChatService:
    def __init__(self, pdf_path: Optional[str] = None):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.llm = llm_gateway
        
        # Models are loaded lazily
        self._embedder = None
        self._reranker = None
        
        self.pdf_path = pdf_path
        self.corpus = []
        self.faiss_index = None
        self.bm25_index = None
        self.corpus_texts = []
        
        if pdf_path and os.path.exists(pdf_path):
            self._initialize_rag()
        else:
            logger.info("No rules.pdf found, skipping RAG initialization.")

    @property
    def embedder(self):
        if self._embedder is None:
            logger.info(f"Loading embedding model on {self.device}...")
            self._embedder = SentenceTransformer(EMBED_MODEL, device=self.device)
        return self._embedder

    @property
    def reranker(self):
        if self._reranker is None:
            logger.info(f"Loading reranking model on {self.device}...")
            self._reranker = CrossEncoder(RERANK_MODEL, device=self.device)
        return self._reranker

    def _initialize_rag(self):
        try:
            self.corpus = self._build_corpus(self.pdf_path)
            if self.corpus:
                self.faiss_index, self.bm25_index, self.corpus_texts = self._build_indices(self.corpus)
                logger.info("RAG indices built successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize RAG: {e}")

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _read_pdf(self, path: str):
        doc = fitz.open(path)
        pages = []
        for i, page in enumerate(doc):
            txt = self._normalize_text(page.get_text("text"))
            if txt:
                pages.append({"page": i + 1, "text": txt})
        return pages

    def _chunk_text(self, text: str, chunk_size=420, overlap=70):
        words = text.split()
        chunks = []
        start = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunk = " ".join(words[start:end]).strip()
            if chunk: chunks.append(chunk)
            if end == len(words): break
            start = end - overlap
        return chunks

    def _build_corpus(self, pdf_path: str):
        pages = self._read_pdf(pdf_path)
        corpus = []
        for p in pages:
            for c in self._chunk_text(p["text"], CHUNK_SIZE_WORDS, CHUNK_OVERLAP_WORDS):
                corpus.append({"page": p["page"], "text": c})
        return corpus

    def _build_indices(self, corpus):
        texts = [x["text"] for x in corpus]
        embeddings = self.embedder.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype("float32")
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)
        tokenized_corpus = [t.lower().split() for t in texts]
        bm25 = BM25Okapi(tokenized_corpus)
        return index, bm25, texts

    def _retrieve_rules(self, query: str):
        if not self.faiss_index:
            return []
            
        # Dense search
        q_emb = self.embedder.encode([query], convert_to_numpy=True, normalize_embeddings=True).astype("float32")
        scores, ids = self.faiss_index.search(q_emb, DENSE_TOP_K)
        dense_results = []
        for score, idx in zip(scores[0], ids[0]):
            if idx != -1:
                item = dict(self.corpus[idx]); item["idx"] = idx; item["retrieval_source"] = "dense"
                dense_results.append(item)
        
        # BM25 search
        q_tokens = query.lower().split()
        bm_scores = self.bm25_index.get_scores(q_tokens)
        best_ids = np.argsort(bm_scores)[::-1][:BM25_TOP_K]
        bm25_results = []
        for idx in best_ids:
            item = dict(self.corpus[idx]); item["idx"] = int(idx); item["retrieval_source"] = "bm25"
            bm25_results.append(item)
            
        # RRF Fusion
        fused = {}
        for results in [dense_results, bm25_results]:
            for rank, item in enumerate(results, start=1):
                idx = item["idx"]
                if idx not in fused:
                    fused[idx] = dict(item); fused[idx]["fused_score"] = 0.0
                fused[idx]["fused_score"] += 1.0 / (60 + rank)
        
        candidates = sorted(fused.values(), key=lambda x: x["fused_score"], reverse=True)[:RERANK_TOP_K]
        if not candidates: return []
        
        # Rerank
        pairs = [[query, item["text"]] for item in candidates]
        rr_scores = self.reranker.predict(pairs)
        for item, score in zip(candidates, rr_scores):
            item["rerank_score"] = float(score)
        
        candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        return candidates[:FINAL_TOP_K]

    def extract_architecture(self, user_text: str):
        prompt = f"""
You are a network architecture extractor. Your job is to convert the user's network description into STRICT JSON.
You MUST always return a JSON object with this structure:
{{
  "components": [{{"id": "R1", "type": "router", "interfaces": 2}}],
  "edges": [{{"from": "R1", "to": "SW1"}}],
  "addressing": {{ "mode": null, "cidrs": [], "base_cidr": null, "subnet_bindings": {{}}, "subnets": [] }},
  "firewall_policy": {{ "mode": null }},
  "user_policies": {{ "allow_auto_addressing": false }}
}}
Rules:
- Extract ALL components and explicit edges.
- Normalize component types: router, switch, server, pc, firewall.
- Set allow_auto_addressing: true if user says 'do it by yourself' or 'automatic' for addressing.
- Return JSON ONLY (no markdown fences if possible, or clear fences).

User description:
{user_text}
"""
        try:
            text = self.llm.generate_text(prompt)
            return self._extract_json(text)
        except Exception as e:
            logger.error(f"Error in extract_architecture: {e}")
            return Architecture().dict()

    def _extract_json(self, text: str):
        text = text.strip()
        try: return json.loads(text)
        except json.JSONDecodeError: pass
        fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced: return json.loads(fenced.group(1))
        obj = re.search(r"\{.*\}", text, re.DOTALL)
        if obj: return json.loads(obj.group(0))
        raise ValueError("Could not parse JSON from response")

    def validate_architecture(self, data: dict):
        missing = []
        components = {c["id"]: c for c in data.get("components", [])}
        if not components:
            missing.append("No components provided.")
            return {"ready": False, "missing": missing}

        # Build adjacency
        adjacency = {cid: [] for cid in components}
        for edge in data.get("edges", []):
            a, b = edge.get("from"), edge.get("to")
            if a in adjacency and b in adjacency:
                adjacency[a].append(b)
                adjacency[b].append(a)

        for cid in adjacency:
            if not adjacency[cid]:
                missing.append(f"What is {cid} connected to?")
            
            comp = components[cid]
            if comp["type"] == "router":
                if comp.get("interfaces") is None:
                    missing.append(f"Router {cid} needs an interface count.")
                elif comp["interfaces"] < len(adjacency[cid]):
                    missing.append(f"Router {cid} needs more interfaces ({len(adjacency[cid])} connections detected).")

        return {"ready": len(missing) == 0, "missing": missing}

    def generate_terraform(self, arch: dict):
        # Build rule query
        types = [c["type"] for c in arch.get("components", [])]
        rule_query = f"AWS Terraform best practices for: {' '.join(set(types))}"
        rules = self._retrieve_rules(rule_query)
        rules_text = "\n\n".join([f"Rule {i}: {r['text']}" for i, r in enumerate(rules, 1)])
        
        prompt = f"""
You are a Terraform expert. Generate a complete, production-ready AWS main.tf based on this architecture:
{json.dumps(arch, indent=2)}

Use these specific rules from documentation if available:
{rules_text if rules else "No specific rules found, use general AWS best practices."}

Instructions:
- Use AWS provider.
- Create VPC, Subnets, Gateways, and Instances.
- Output ONLY the Terraform code within ```hcl fences.
- Add a summary segment at the beginning starting with ===MAPPING_SUMMARY===.
"""
        try:
            return self.llm.generate_text(prompt)
        except Exception as e:
            logger.error(f"Error generating Terraform: {e}")
            return "Error generating Terraform code."

# Singleton instance
chat_service = ChatService(pdf_path=RULES_PDF_PATH)
