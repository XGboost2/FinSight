# PROJECT.md — FinSight AI

> Drop this in the repo root. Claude Code, Cursor, Copilot, and Gemini Code Assist
> all read this automatically for instant project context.

---

## What Is This

**FinSight AI** — Financial Risk Intelligence Platform
- Analyses SEC EDGAR 10-K filings using a multi-agent RAG system
- Extracts risk factors, financial metrics, generates structured risk reports
- Built to demonstrate production-grade AI engineering for EU job applications

---

## Current State

- **Day 1 of 100** — Hello World FastAPI + Dockerising
- No agents yet · No RAG yet · No vector DB yet
- Foundation being laid — everything builds on top of this

---

## Target Architecture (Day 70)

```
┌─────────────────────────────────────────────┐
│              FinSight AI                    │
├─────────────────────────────────────────────┤
│  FastAPI (REST + GraphQL endpoint)          │
│           ↕                                 │
│  LangGraph Workflow                         │
│  ingest → extract → analyze → report       │
├─────────────────────────────────────────────┤
│  CrewAI Agent Crew                          │
│  ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
│  │Researcher│ │ Analyst  │ │Report Writer│ │
│  └──────────┘ └──────────┘ └─────────────┘ │
├─────────────────────────────────────────────┤
│  Qdrant — hybrid search (BM25 + dense)      │
│  SEC EDGAR 10-K filing chunks               │
├─────────────────────────────────────────────┤
│  LangFuse (tracing) · RAGAS (evals)         │
│  PostHog (user analytics)                   │
├─────────────────────────────────────────────┤
│  Redis (LLM cache + Celery broker)          │
│  Celery (async task queue)                  │
├─────────────────────────────────────────────┤
│  Docker → GCP Cloud Run (live public URL)   │
└─────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer          | Technology                                          |
|----------------|-----------------------------------------------------|
| **Frontend**   | React 19 · Vite 8 · Axios · Lucide React           |
| **API**        | FastAPI · Pydantic · strawberry-graphql             |
| **LLM**        | Anthropic Claude (primary) · OpenAI (fallback)      |
| **Model Router** | Simple classifier: cheap ↔ powerful by complexity |
| **Agents**     | LangGraph · CrewAI · Pydantic AI                    |
| **RAG**        | Qdrant · sentence-transformers · rank-bm25          |
| **Embeddings** | sentence-transformers (free, local) · fastembed (Qdrant) · OpenAI/Cohere (optional cloud) |
| **LLMOps**     | LangFuse · RAGAS · LangSmith · PostHog              |
| **Security**   | presidio-analyzer · guardrails-ai                   |
| **Cache**      | Redis (LLM response cache — SHA256 keyed + TTL)     |
| **Async**      | Celery · Redis broker · asyncio                     |
| **Containers** | Docker · docker-compose                             |
| **Cloud**      | GCP Cloud Run · Artifact Registry                   |
| **Data**       | SEC EDGAR API · pypdf · httpx · tiktoken            |

---

## Project Structure

```
finsight-ai/
├── CLAUDE.md                  ← AI context (Claude)
├── PROJECT.md                 ← This file
├── SKILLS.md                  ← Developer skill levels
├── docker-compose.yml         ← All services (backend + frontend + redis + qdrant)
├── .env.example               ← Env var template (never commit .env)
│
├── backend/
│   ├── Dockerfile             ← Backend container
│   ├── requirements.txt       ← Python dependencies
│   ├── main.py                ← FastAPI entry point
│   ├── config.py              ← Settings / env loader
│   ├── api/
│   │   ├── routes.py          ← REST endpoints
│   │   └── graphql.py         ← GraphQL schema
│   ├── agents/
│   │   ├── graph.py           ← LangGraph workflow
│   │   └── crew.py            ← CrewAI agent crew
│   ├── rag/
│   │   ├── pipeline.py        ← RAG pipeline
│   │   ├── retriever.py       ← Qdrant hybrid search
│   │   └── embedder.py        ← Embedding logic
│   ├── ingestion/
│   │   ├── edgar.py           ← SEC EDGAR fetcher
│   │   └── chunker.py         ← Document chunker
│   ├── cache/
│   │   └── llm_cache.py       ← Redis LLM response cache
│   ├── evaluation/
│   │   └── ragas_eval.py      ← RAGAS evaluation runner
│   ├── security/
│   │   ├── input_guard.py     ← Prompt injection defense
│   │   └── pii_filter.py      ← PII detection + filtering
│   └── models/
│       └── schemas.py         ← Pydantic data models
│
├── frontend/
│   ├── Dockerfile             ← Frontend container
│   ├── package.json           ← NPM dependencies
│   ├── vite.config.js         ← Vite build config
│   ├── index.html             ← SPA entry point
│   ├── public/
│   │   ├── favicon.svg
│   │   └── icons.svg          ← Shared icon sprites
│   └── src/
│       ├── main.jsx           ← React root mount
│       ├── App.jsx            ← App shell + router
│       ├── index.css          ← Global styles + design tokens
│       ├── assets/            ← Static images / SVGs
│       ├── components/        ← Reusable UI (future)
│       │   ├── Navbar.jsx
│       │   ├── FilingCard.jsx
│       │   ├── RiskChart.jsx
│       │   ├── ChatPanel.jsx
│       │   └── LoadingSpinner.jsx
│       ├── pages/             ← Route-level views (future)
│       │   ├── Dashboard.jsx  ← Main dashboard — filing overview + risk heatmap
│       │   ├── Filing.jsx     ← Single filing deep-dive
│       │   ├── Chat.jsx       ← LLM Q&A interface
│       │   └── Settings.jsx   ← API key config / preferences
│       ├── hooks/             ← Custom React hooks (future)
│       │   ├── useFilings.js
│       │   └── useChat.js
│       ├── services/          ← API client layer (future)
│       │   └── api.js         ← Axios instance + endpoints
│       └── utils/             ← Helpers (future)
│           └── formatters.js  ← Date, currency, number formatters
│
├── tests/
│   ├── eval_baseline/
│   │   └── questions.json     ← 10 hand-curated Q&A pairs (Week 2)
│   └── unit/
│
└── infra/
    └── gcp/
        └── cloudrun.yaml      ← GCP Cloud Run config
```

---

## Coding Standards

### Backend (Python)
- **Python 3.11+** — type hints everywhere, no bare `except`
- **Pydantic** for all data models — never raw dicts for structured data
- **async/await** for all I/O — no blocking calls in async context
- **Error handling** — never silent failures, always log with context
- **LLM calls** — always log: `model`, `tokens_in`, `tokens_out`, `cost_usd`

### Frontend (React)
- **React 19** — functional components + hooks only, no class components
- **Vanilla CSS** — design tokens in `index.css`, no TailwindCSS
- **Axios** via `services/api.js` — centralised API client, never raw `fetch`
- **Lucide React** for icons — consistent icon set across all views
- **Component naming** — PascalCase files, one component per file
- **State** — `useState` / `useReducer` for local, lift to App for shared
- **Error boundaries** — wrap route-level pages, show user-friendly fallback

### General
- **Docker** — everything runs in Docker, local dev uses docker-compose
- **Commits** — conventional: `feat:` `fix:` `chore:` `docs:` `test:`
- **Secrets** — never commit `.env`, always use `.env.example` as template

---

## Eval Baseline (create in Week 2)

10 hand-curated Q&A pairs. Run every single week to catch quality regression.

```
tests/eval_baseline/questions.json
```

```json
[
  {
    "question": "What are Apple's top 3 risk factors in their 2023 10-K?",
    "expected_topics": ["supply chain", "competition", "regulation"],
    "source_filing": "AAPL_10K_2023"
  }
]
```

**Rule:** If RAGAS faithfulness score drops below baseline — stop and fix retrieval before adding features.

---

## LLM Cache Pattern

All LLM responses cached via Redis. See `app/cache/llm_cache.py`.

- Cache key: `llm_cache:{sha256(query+model+filing_id)}`
- TTL: 30 days for filing summaries, 7 days for analysis, 1 day default
- Never let cache failure break the main flow — always catch exceptions silently

---

## Model Router

```python
# Simple complexity classifier
CHEAP_MODEL  = "gpt-4o-mini"    # simple lookups, single-doc queries
POWER_MODEL  = "gpt-4o"         # multi-doc analysis, complex reasoning

def route_model(query: str) -> str:
    # classify complexity → return model name
    ...
```

Document cost savings in LangFuse dashboard — this becomes your interview story.

---

## Key Constraints

- **No hallucination** — all answers grounded in SEC data, citations required
- **GDPR** — EU deployment, no PII stored, presidio filters all outputs
- **Cost tracking** — every LLM call logs cost, visible in LangFuse
- **Graphify** — developer uses token compression, keep code comments dense

---

## API Accounts & Keys

Every service below needs a signup + API key. Store all keys in `.env` (never commit).

| #  | Service                  | What For                              | Signup URL                                      | Env Variable(s)                     | Free Tier?       |
|----|--------------------------|---------------------------------------|--------------------------------------------------|--------------------------------------|------------------|
| 1  | **Anthropic**            | Claude LLM (primary model)            | https://console.anthropic.com                    | `ANTHROPIC_API_KEY`                  | Pay-as-you-go    |
| 2  | **OpenAI**               | GPT fallback + embeddings             | https://platform.openai.com                      | `OPENAI_API_KEY`                     | $5 free credits  |
| 3  | **Qdrant Cloud**         | Managed vector DB (or self-host)      | https://cloud.qdrant.io                          | `QDRANT_URL`, `QDRANT_API_KEY`       | ✅ 1GB free       |
| 4  | **SEC EDGAR**            | 10-K filing data (requires User-Agent)| https://www.sec.gov/os/accessing-edgar-data       | `SEC_EDGAR_USER_AGENT`               | ✅ Free (public)  |
| 5  | **LangFuse**             | LLM tracing + observability           | https://cloud.langfuse.com                       | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | ✅ Free tier |
| 6  | **LangSmith** *(optional)* | LangChain tracing (alt to LangFuse) | https://smith.langchain.com                      | `LANGCHAIN_API_KEY`                  | ✅ Free tier      |
| 7  | **PostHog**              | User analytics + feature flags        | https://app.posthog.com/signup                   | `POSTHOG_API_KEY`, `POSTHOG_HOST`    | ✅ 1M events free |
| 8  | **Google Cloud (GCP)**   | Cloud Run deployment + Artifact Registry | https://console.cloud.google.com              | `GCP_PROJECT_ID`, `GCP_REGION`       | ✅ $300 credits   |
| 9  | **Cohere** *(optional)*  | Cloud embeddings + reranker (if not using local) | https://dashboard.cohere.com           | `COHERE_API_KEY`                     | ✅ Free tier      |
| 10 | **Redis Cloud** *(optional)* | Managed Redis (or self-host via Docker) | https://app.redislabs.com                   | `REDIS_URL`                          | ✅ 30MB free      |
| 11 | **HuggingFace** *(optional)* | Download gated models (most don't need this) | https://huggingface.co/settings/tokens   | `HF_TOKEN`                           | ✅ Free           |

### Free Embedding Models (no API key needed)

These run **locally** via `sentence-transformers` or `fastembed` — zero cost, no signup:

| Model                              | Dim  | Size   | Speed   | Quality | Best For                       |
|------------------------------------|------|--------|---------|---------|--------------------------------|
| `all-MiniLM-L6-v2`                | 384  | 80 MB  | ⚡ Fast  | Good    | Prototyping, dev/test          |
| `BAAI/bge-small-en-v1.5`          | 384  | 130 MB | ⚡ Fast  | Better  | Production (small)             |
| `BAAI/bge-base-en-v1.5`           | 768  | 440 MB | Medium  | Great   | Production (balanced)          |
| `nomic-ai/nomic-embed-text-v1.5`  | 768  | 550 MB | Medium  | Great   | Long docs (8192 token context) |
| `Qdrant/fastembed` *(wrapper)*     | 384  | 80 MB  | ⚡ Fast  | Good    | Qdrant-native, easiest setup   |

**Recommended path:** Start with `all-MiniLM-L6-v2` (fastest to prototype), upgrade to `bge-base-en-v1.5` for production.

### Priority Order

Sign up in this order based on when you'll need them:

1. **Day 1–7:** SEC EDGAR (free, just set User-Agent) → OpenAI or Anthropic (for first LLM call)
2. **Day 7–14:** Embeddings (free — `pip install sentence-transformers`, no key!) → Qdrant (run locally via Docker)
3. **Day 14–49:** LangFuse → PostHog
4. **Day 49+:** GCP → Redis Cloud (if not self-hosting) → HuggingFace

### `.env.example` Template

```env
# === LLM ===
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
COHERE_API_KEY=              # optional — only if using cloud embeddings

# === Vector DB ===
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=              # only for Qdrant Cloud

# === Data ===
SEC_EDGAR_USER_AGENT=FinSight your@email.com

# === Observability ===
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
LANGCHAIN_API_KEY=           # optional
POSTHOG_API_KEY=phc_...
POSTHOG_HOST=https://eu.posthog.com

# === Infra ===
REDIS_URL=redis://localhost:6379
GCP_PROJECT_ID=
GCP_REGION=europe-west1
HF_TOKEN=                    # optional
```

---

## Milestones

| Day    | Milestone                                        |
|--------|--------------------------------------------------|
| 1      | Hello World FastAPI + Dockerised ← NOW           |
| 7      | SEC EDGAR ingestion + basic LLM Q&A              |
| 14     | RAG pipeline + eval baseline (10 Q&A pairs)      |
| 21     | Entity extraction → structured JSON              |
| 28     | First Pydantic AI agent (type-safe)              |
| 35     | LangGraph multi-step workflow                    |
| 42     | CrewAI crew (3 roles) + security layer           |
| 49     | LangFuse tracing + RAGAS evals                   |
| 51–55  | 🏅 CCA Exam                                      |
| 56     | Qdrant hybrid search (BM25 + dense)              |
| 63     | Model routing + cost dashboard                   |
| 70     | 🚀 Live on GCP Cloud Run                         |
| 77     | LoRA/QLoRA fine-tuning experiment                |
| 84     | GraphRAG + knowledge graph layer                 |
| 91     | Portfolio + LinkedIn posts                       |
| 92–100 | 15 applications + interviews + offer 🎯          |
