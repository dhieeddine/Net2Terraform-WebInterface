# Notebook purpose and app integration guide

## What the notebook does (final-rag.ipynb)

The notebook builds a full, end-to-end pipeline that turns a natural-language network description into Terraform (and optionally Ansible). It is organized as a sequence of modules written to disk, then executed in a controlled flow. The key stages are:

1) Bootstrap and configuration
   - Creates a working project tree under /kaggle/working/net2tf_v3
   - Defines paths for kb/, index/, templates/, generated/
   - Sets model names and RAG parameters

2) Core pipeline modules (written via write_file)
   - extractor.py: parses user text into a structured architecture JSON
   - validator.py: checks the architecture for missing or inconsistent inputs
   - addressing.py: assigns or validates CIDR blocks and subnets
   - planner.py: builds a cloud-domain plan (peering vs. tgw, public/private split, NAT)
   - retriever.py: loads kb/*.md, builds FAISS index, and does RAG retrieval
   - plan_guard.py / spec_guard.py / quality_checks.py: policy and correctness checks
   - terraform_builder.py: renders Terraform from Jinja templates
   - response_renderer.py: builds the final response payload
   - app.py: provides compile_prompt() which orchestrates the full flow

3) Terraform and Ansible output
   - Writes generated Terraform to generated/
   - Optionally builds Ansible inventory and playbooks
   - Supports optional deploy and destroy helpers (deploy_check.py)

4) Evaluation suites
   - eval_suite.py / eval_snapshots.py / eval_mesh_star.py
   - Runs multiple regression tests against compile_prompt()
   - Produces pass/fail results and summary JSON

In short: the notebook is not just a demo; it is the source of truth for the complete pipeline and regression tests.


## What the app currently uses

The app uses a simplified pipeline located in backend/app/services/chat_service.py. It does:

- LLM-based extraction of architecture JSON
- A PDF-based RAG flow over backend/rules.pdf
- A single Terraform generation prompt

It does NOT include the notebook modules (extractor/planner/guards/terraform_builder), and the test-evaluation route currently uses a simulated result.


## What you need to integrate properly

To align the app with the notebook, you should port the notebook modules and wire the real pipeline into the API. Use this checklist:

1) Move notebook modules into the app
   - Create backend/app/services/ for the notebook modules
   - Port these files from the notebook output:
     - app.py (compile_prompt entrypoint)
     - extractor.py, validator.py, addressing.py
     - retriever.py
     - planner.py
     - plan_guard.py, spec_guard.py, quality_checks.py
     - terraform_builder.py, response_renderer.py
     - ansible_planner.py, ansible_builder.py, ansible_check.py (optional)
     - templates/main.tf.j2 and templates/variables.tf.j2

2) Add notebook configuration to backend/app/core/config.py
   - KB_DIR, INDEX_DIR, GENERATED_DIR, TEMPLATES_DIR
   - EMBED_MODEL, RERANK_MODEL, TOP_K, MAX_CHARS_PER_CHUNK
   - Make these paths point to the repo (not /kaggle/working/...)

3) Provide the KB markdowns
   - The notebook expects kb/*.md files
   - Place them in repo root: kb/
   - Example files: mapping_rules.md, peering.md, tgw.md, security_patterns.md
   - Build or load the FAISS index using retriever.py

4) Wire compile_prompt into the API
   - In backend/app/routes/test_evaluation.py, replace the simulated result
   - Call compile_prompt(prompt=..., out_dir=...)
   - Return real outputs from the pipeline

5) Update chat service usage
   - Either replace chat_service flow with the compile_prompt pipeline
   - Or keep chat_service for interactive use, but expose compile_prompt for testing

6) Validate with notebook tests
   - Port evaluation tests from eval_suite.py
   - Run them via API or a script to confirm alignment


## Recommended integration order

1. Port retriever.py + config settings + kb/ files (RAG foundations)
2. Port extractor/validator/addressing/planner
3. Port terraform_builder + templates
4. Add compile_prompt to backend services and wire /api/test/run
5. Run evaluation suite and fix deviations


## Notes on data sources

- Notebook RAG uses kb/*.md files, not rules.pdf
- App RAG uses rules.pdf
- You can keep both, but the notebook logic is built around markdown KB


## Summary

If you want the app to behave exactly like the notebook, you must port the notebook modules and use compile_prompt() as the backend entrypoint. Otherwise, the app will continue to run a simplified pipeline that does not match the notebook's tests.
