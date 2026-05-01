# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Developer: Kural

- **Role:** Senior Software Engineer → transitioning to AI Engineer
- **Experience:** ~7 years, Python/Flask backend + ML pipelines
- **Location:** Prague, Czech Republic (EU work authorisation)
- **Timeline:** 100-day AI engineering upskill (started April 2026)
- **Token efficiency:** Uses Graphify — keep responses dense, structured, no fluff

---

## What Kural Already Knows (skip basics on these)

- Python, Flask, Celery, Redis, PostgreSQL, REST APIs, Git, Docker, Linux/Bash
- ML pipelines: scikit-learn, PyCaret, Keras
- Built **Wiglaf** risk platform at Barclays — 26 production versions, real financial risk
- Production CI/CD, monitoring, versioning discipline, async patterns, Pydantic, FastAPI

## What Kural Is Learning (intermediate guidance — not beginner)

- LLM APIs: Anthropic Claude, OpenAI — structured outputs, function calling
- RAG, vector databases, embeddings, RAGAS evaluation
- LangGraph, CrewAI, Pydantic AI, MCP
- LLMOps: LangFuse, cost tracking, A/B prompt testing
- GCP Cloud Run deployment, LoRA/QLoRA fine-tuning, GraphRAG

---

## This Project: FinSight AI

**What:** Financial Risk Intelligence Platform analysing SEC EDGAR 10-K filings via multi-agent RAG  
**Why:** Portfolio centrepiece for EU AI engineering job applications  
**Current state:** Day 1 — Hello World FastAPI + React frontend, Dockerised  

---

## Dev Commands

```bash
# Start everything (backend :8000, frontend :3000)
docker-compose up --build

# Backend only
docker-compose up backend

# Detached
docker-compose up -d

# Rebuild after dependency changes
docker-compose up --build --force-recreate

# Backend hot-reloads via volume mount — no rebuild needed for .py edits
# Frontend hot-reloads via Vite + CHOKIDAR_USEPOLLING=true

# Run backend locally without Docker
cd backend && uvicorn main:app --reload

# Check API
curl http://localhost:8000/health
curl http://localhost:8000/
```

No tests exist yet. When added they'll live in `tests/` at root.

---

## Current Repo Structure

```
finsight-ai/
├── CLAUDE.md / PROJECT.md / SKILLS.md
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── main.py          ← FastAPI app (entry point)
│   └── requirements.txt
└── frontend/
    ├── Dockerfile
    ├── src/App.jsx      ← React + Vite, polls / on load to show API status
    └── vite.config.js
```

**Note:** PROJECT.md shows a target `app/` structure — that's the Day 70 goal, not what exists now. Build into `backend/` for now, refactor to `app/` when the structure warrants it.

---

## Target Architecture (Day 70)

```
FastAPI (REST + GraphQL)
    ↕
LangGraph Workflow: ingest → extract → analyze → report
    ↕
CrewAI Crew: Researcher | Analyst | Report Writer
    ↕
Qdrant (BM25 + dense hybrid search) — SEC EDGAR 10-K chunks
    ↕
Redis: LLM cache (SHA256 key, 30d TTL) + Celery broker
    ↕
LangFuse (tracing) · RAGAS (evals) · PostHog (analytics)
    ↕
Docker → GCP Cloud Run
```

**Tech:** FastAPI + Pydantic · Anthropic Claude (primary) + OpenAI (fallback) · LangGraph · CrewAI · Pydantic AI · Qdrant · sentence-transformers · rank-bm25 · Redis · Celery · presidio-analyzer · guardrails-ai · strawberry-graphql

---

## Code Standards

- Python 3.11+ · type hints everywhere · no bare `except`
- Pydantic for all structured data — never raw dicts
- `async/await` for all I/O — no blocking calls in async context
- Every LLM call logs: `model`, `tokens_in`, `tokens_out`, `cost_usd`
- Cache key pattern: `llm_cache:{sha256(query+model+filing_id)}`
- Cache TTL: 30d filing summaries · 7d analysis · 1d default — failures must not break main flow
- No hallucination — RAG answers grounded in SEC data, citations required
- GDPR — EU deployment, presidio filters all outputs, no PII stored
- Conventional commits: `feat:` `fix:` `chore:` `docs:` `test:`
- Everything runs in Docker — if it doesn't work in Docker, it doesn't count

---

## Model Router Pattern

```python
CHEAP_MODEL  = "claude-haiku-4-5"   # simple lookups, single-doc queries
POWER_MODEL  = "claude-opus-4-6"    # multi-doc analysis, complex reasoning
```

Document cost savings in LangFuse — becomes an interview story.

---

## Eval Baseline (create Week 2)

10 hand-curated Q&A pairs at `tests/eval_baseline/questions.json`. Run weekly.  
**Rule:** If RAGAS faithfulness drops below baseline — stop, fix retrieval, don't add features.

---

## How Claude Should Respond

- Direct. No preamble. Get to the point.
- Honest. If something is wrong, say so. Don't sugarcoat.
- Production-quality code — error handling, async, structured logging.
- Explain WHY, not just what. Call out antipatterns directly.
- Connect advice to FinSight AI use cases.
- Don't explain what RAG, LangGraph, Docker, FastAPI, Celery, or Pydantic is.
- Don't write entire files without explaining what they do.
- Push toward building over watching. Flag tutorial hell immediately.

---

## Resources

- 100-day roadmap: https://www.notion.so/34bc0be3471481f289addc0e411316d5
- CCA exam prep: https://claudecertifications.com

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
