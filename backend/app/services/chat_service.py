import os
import re
import json
import math
import logging
import hashlib
import pickle
import torch
import numpy as np
import ipaddress
from pathlib import Path
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
RAG_RECALL_MULTIPLIER = 3
RAG_MIN_RECALL_K = 14

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
        self.rag_ready = False
        self.rag_error: str | None = None
        
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
                self.faiss_index, self.bm25_index, self.corpus_texts = self._build_or_load_indices(self.corpus)
                self.rag_ready = True
                self.rag_error = None
                logger.info("RAG indices ready. chunks=%d", len(self.corpus))
            else:
                self.rag_ready = False
                self.rag_error = "rules source parsed but produced zero chunks"
                logger.warning("RAG initialization skipped because chunk list is empty")
        except Exception as e:
            self.rag_ready = False
            self.rag_error = str(e)
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

    def _pdf_fingerprint(self) -> str:
        path = Path(self.pdf_path or "")
        if not path.exists():
            return "missing"
        stat = path.stat()
        raw = f"{path.resolve()}::{stat.st_mtime_ns}::{stat.st_size}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def _cache_paths(self) -> tuple[Path, Path]:
        root = Path(__file__).resolve().parents[2]
        cache_dir = root / "rag_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        stamp = self._pdf_fingerprint()
        return (
            cache_dir / f"rules_{stamp}.index",
            cache_dir / f"rules_{stamp}.pkl",
        )

    def _build_or_load_indices(self, corpus):
        index_path, meta_path = self._cache_paths()
        if index_path.exists() and meta_path.exists():
            try:
                index = faiss.read_index(str(index_path))
                with meta_path.open("rb") as handle:
                    payload = pickle.load(handle)

                texts = payload.get("texts", []) if isinstance(payload, dict) else []
                tokenized = payload.get("tokenized", []) if isinstance(payload, dict) else []
                if not texts or not tokenized:
                    raise ValueError("Cached RAG metadata is incomplete")

                bm25 = BM25Okapi(tokenized)
                logger.info("Loaded cached RAG index from %s", index_path)
                return index, bm25, texts
            except Exception as exc:
                logger.warning("Invalid RAG cache detected, rebuilding index: %s", exc)
                try:
                    index_path.unlink(missing_ok=True)
                    meta_path.unlink(missing_ok=True)
                except Exception:
                    pass

        index, bm25, texts = self._build_indices(corpus)
        tokenized = [t.lower().split() for t in texts]
        faiss.write_index(index, str(index_path))
        with meta_path.open("wb") as handle:
            pickle.dump({"texts": texts, "tokenized": tokenized}, handle)
        logger.info("Built and cached RAG index at %s", index_path)
        return index, bm25, texts

    def _query_expansions(self, query: str) -> list[str]:
        lower = query.lower()
        expanded = [query]

        if "bastion" in lower:
            expanded.extend([
                "bastion host public ssh jump host",
                "private hosts ssh only from bastion",
            ])
        if "nat" in lower or "outbound" in lower or "internet" in lower:
            expanded.extend([
                "private subnet outbound internet nat gateway",
                "nat gateway route table private subnet",
            ])
        if "router" in lower and "switch" in lower:
            expanded.append("router switch mapping vpc subnet design")
        if "firewall" in lower or "security group" in lower:
            expanded.append("firewall as security group defaults")

        out: list[str] = []
        seen: set[str] = set()
        for item in expanded:
            key = item.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _metadata_boost(self, query: str, text: str) -> float:
        q = query.lower()
        t = text.lower()
        boost = 0.0

        if "bastion" in q and "bastion" in t:
            boost += 0.8
        if ("nat" in q or "internet" in q) and ("nat" in t or "internet gateway" in t):
            boost += 0.7
        if "security group" in q and "security group" in t:
            boost += 0.6
        if "transit gateway" in q and "transit gateway" in t:
            boost += 0.9
        if "peering" in q and "peering" in t:
            boost += 0.8

        return boost

    def _retrieve_rules(self, query: str):
        if not self.faiss_index:
            return []

        recall_k = max(RAG_MIN_RECALL_K, FINAL_TOP_K * RAG_RECALL_MULTIPLIER)
        dense_candidates: dict[int, float] = {}
        for expanded_query in self._query_expansions(query):
            q_emb = self.embedder.encode([expanded_query], convert_to_numpy=True, normalize_embeddings=True).astype("float32")
            scores, ids = self.faiss_index.search(q_emb, recall_k)
            for score, idx in zip(scores[0], ids[0]):
                if idx < 0:
                    continue
                dense_candidates[idx] = max(float(score), dense_candidates.get(idx, float("-inf")))

        bm25_candidates: dict[int, float] = {}
        bm25_scores = self.bm25_index.get_scores(query.lower().split())
        for idx in np.argsort(bm25_scores)[::-1][:max(BM25_TOP_K, recall_k)]:
            bm25_candidates[int(idx)] = float(bm25_scores[idx])

        fused: dict[int, dict[str, float | int]] = {}
        for rank, (idx, score) in enumerate(sorted(dense_candidates.items(), key=lambda x: x[1], reverse=True), start=1):
            fused[idx] = {
                "idx": idx,
                "vector_score": score,
                "bm25_score": bm25_candidates.get(idx, 0.0),
                "rrf": 1.0 / (60 + rank),
            }

        for rank, (idx, score) in enumerate(sorted(bm25_candidates.items(), key=lambda x: x[1], reverse=True), start=1):
            if idx not in fused:
                fused[idx] = {"idx": idx, "vector_score": dense_candidates.get(idx, 0.0), "bm25_score": score, "rrf": 0.0}
            fused[idx]["rrf"] = float(fused[idx]["rrf"]) + (1.0 / (60 + rank))

        candidates = sorted(fused.values(), key=lambda x: float(x["rrf"]), reverse=True)[:RERANK_TOP_K]
        if not candidates:
            return []

        pairs = [[query, self.corpus[int(item["idx"])]["text"]] for item in candidates]
        rr_scores = self.reranker.predict(pairs)

        rescored = []
        for item, rr in zip(candidates, rr_scores):
            idx = int(item["idx"])
            text = self.corpus[idx]["text"]
            meta_boost = self._metadata_boost(query, text)
            final_score = (
                0.30 * float(item["vector_score"])
                + 0.25 * float(rr)
                + 0.25 * float(item["rrf"])
                + 1.00 * float(meta_boost)
            )
            row = dict(self.corpus[idx])
            row["idx"] = idx
            row["vector_score"] = float(item["vector_score"])
            row["bm25_score"] = float(item["bm25_score"])
            row["rerank_score"] = float(rr)
            row["metadata_boost"] = float(meta_boost)
            row["final_score"] = float(final_score)
            rescored.append(row)

        rescored.sort(key=lambda x: x["final_score"], reverse=True)
        return rescored[:FINAL_TOP_K]

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
