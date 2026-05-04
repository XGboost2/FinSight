# FinSight AI

**Financial Risk Intelligence Platform** — ingests SEC EDGAR 10-K filings, stores them as vector embeddings, and answers natural language questions grounded in source documents.

Built as a portfolio project demonstrating production-grade AI engineering: RAG pipeline, XBRL financial data parsing, multi-provider LLM routing, and real-time company comparison.

---

## Features

| Feature | Detail |
|---------|--------|
| **10-K Ingest** | Fetches latest SEC EDGAR 10-K, chunks, embeds with BGE, stores in Qdrant. Idempotent — re-ingesting is a no-op unless `?force=true` |
| **RAG Q&A** | Semantic search over filing chunks → grounded LLM answer with source citations and cost metadata |
| **XBRL Financials** | Revenue, net income, gross margin, YoY growth pulled directly from SEC EDGAR XBRL API — deterministic, no LLM guessing |
| **Dashboard** | Per-company metrics card + executive summary, risk factors, revenue segments, management outlook |
| **10-K Analysis Report** | Full fundamental analysis: company overview, findings table (revenue/profitability/risk/sentiment), risk gauge (0–100), management sentiment score, bull/bear cases, verdict. XBRL + multi-query RAG + LLM synthesis. Cached 24h, `?refresh=true` to regenerate |
| **Side-by-side Compare** | Two-ticker head-to-head: financial bar charts, YoY revenue trend, compact analysis reports for both companies, pros/cons, strategic verdict |
| **LLM Cost Tracker** | Every API call atomically records cost (USD), token counts, and model name to Redis. Aggregates across day/week/month with per-model breakdown. Viewable via `$` button in topbar |
| **Model Selector** | Choose DeepSeek Chat/Reasoner, Claude Haiku/Sonnet/Opus, or GPT-4o from the chat panel |
| **Smart Model Router** | Auto-routes simple queries to cheap model, complex reasoning queries to power model |
| **Company Search** | Autocomplete across ~13k SEC-registered companies via Redis — zero API calls at query time |
| **Live Charts** | TradingView price charts on dashboard and compare screens |
| **Health Monitoring** | Redis + Qdrant status indicators in the topbar, polling every 30s |

---

## Architecture

```
React (Vite) :3000
      │
      ▼
FastAPI :8000  ──  APScheduler (daily 02:00 UTC ticker refresh)
      │
      ├── ingestion/
      │     edgar.py       ← SEC EDGAR API → 10-K HTML/text
      │     chunker.py     ← paragraph-aware chunking, 1000 char / 200 overlap
      │     xbrl.py        ← XBRL financial facts (revenue, income, margin, YoY)
      │
      ├── rag/
      │     embedder.py    ← fastembed + BAAI/bge-base-en-v1.5 (ONNX, CPU, no torch)
      │     retriever.py   ← Qdrant upsert + query_points with filing_id filter
      │     pipeline.py    ← ingest() and retrieve() orchestration
      │
      ├── services/
      │     llm.py         ← DeepSeek (primary) → Anthropic → OpenAI → mock
      │     dashboard.py   ← XBRL metrics + LLM narrative extraction, Redis cache
      │     report.py      ← 10-K fundamental analysis: findings table, bull/bear, verdict
      │     comparison.py  ← two-ticker LLM analysis, Redis cache
      │
      ├── cache/
      │     ticker_cache.py    ← SEC ticker → CIK, Redis hash
      │     filing_registry.py ← ingested ticker registry, filing-type aware keys
      │     cost_tracker.py    ← LLM call cost recording, day/week/month aggregation
      │     redis_client.py    ← Redis singleton
      │
      ├── api/routes.py    ← all REST endpoints, Pydantic I/O, per-request logging
      ├── logging_config.py← rotating file logger → backend/logs/finsight.log
      └── config.py        ← Pydantic Settings, all env vars
      │
      ▼               ▼
   Qdrant :6333     Redis :6379
```

**LLM routing (auto, overridable per-request):**

| Query type | Model | Cost / 1M tokens |
|------------|-------|-----------------|
| Simple fact lookup | `deepseek-chat` | $0.07 in / $0.28 out |
| Complex reasoning, comparison, "why" | `deepseek-reasoner` | $0.55 in / $2.19 out |
| User override | Any of 8 models | — |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI 0.110+, Pydantic v2, uvicorn |
| Embeddings | fastembed 0.3.6 + `BAAI/bge-base-en-v1.5` (ONNX, no torch, 768-dim) |
| Vector DB | Qdrant 1.9+ (cosine similarity, filing-scoped filters) |
| LLM | DeepSeek (primary) · Anthropic Claude · OpenAI (all switchable) |
| Financial Data | SEC EDGAR XBRL API (deterministic, no LLM extraction) |
| Cache | Redis 8 (ticker index, filing registry, dashboard cache 7d TTL) |
| Scheduler | APScheduler 3.10 |
| Ingestion | SEC EDGAR REST API via httpx |
| Frontend | React 19 + Vite, TradingView charts, Lucide icons |
| Testing | pytest + httpx (backend) · vitest + React Testing Library (frontend) |
| Containers | Docker + Docker Compose |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/companies/{ticker}/ingest` | Fetch + embed 10-K. Add `?force=true` to re-ingest |
| `POST` | `/api/chat` | RAG Q&A with optional `model` override |
| `GET` | `/api/companies/search?q=apple` | Company autocomplete from Redis |
| `GET` | `/api/companies/{ticker}/dashboard` | XBRL metrics + LLM narrative |
| `GET` | `/api/companies/{ticker}/report` | Full 10-K analysis report. Add `?refresh=true` to regenerate |
| `POST` | `/api/companies/compare` | Head-to-head comparison with YoY trends |
| `GET` | `/api/admin/costs` | LLM cost breakdown by day/week/month, per model |
| `POST` | `/api/admin/refresh-tickers` | Manually refresh ticker cache |
| `GET` | `/api/health` | Redis + Qdrant status + filing count |
| `GET` | `/docs` | Swagger UI |

### Example: Ingest + Query

```bash
# Ingest Apple's latest 10-K
curl -X POST http://localhost:8000/api/companies/AAPL/ingest

# Ask a question (auto model routing)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "question": "What are the main risk factors?"}'

# Ask with a specific model
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "question": "Analyse revenue trends", "model": "deepseek-reasoner"}'

# Compare two companies
curl -X POST http://localhost:8000/api/companies/compare \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL", "MSFT"]}'
```

---

## Quickstart

### Docker (recommended)

```bash
cp .env.example .env   # add your API keys
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |
| Qdrant dashboard | http://localhost:6333/dashboard |

### Local (no Docker)

```bash
# Backend
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Infrastructure (still needs Docker)
docker compose up qdrant redis
```

### Tests

```bash
# Backend
pip install -r backend/requirements-test.txt
pytest

# Frontend
cd frontend && npm install && npm test
```

---

## Environment Variables

```env
# LLM — DeepSeek is cheapest (~10x vs Claude Haiku)
DEEPSEEK_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...   # optional fallback
OPENAI_API_KEY=sk-...          # optional fallback

# Infrastructure — defaults match docker-compose
QDRANT_URL=http://qdrant:6333
REDIS_URL=redis://redis:6379

# Reserved (not yet wired)
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
ALPHA_VANTAGE_KEY=
```

---

## Repo Structure

```
finsight-ai/
├── docker-compose.yml
├── pytest.ini
├── FEATURES.md              ← full feature backlog with implementation plans
├── backend/
│   ├── main.py              ← FastAPI entry, lifespan, request logging middleware
│   ├── config.py            ← Pydantic Settings
│   ├── logging_config.py    ← rotating file logger (10MB × 5 backups)
│   ├── requirements.txt
│   ├── requirements-test.txt
│   ├── logs/                ← finsight.log (gitignored)
│   ├── api/routes.py        ← all endpoints
│   ├── models/schemas.py    ← Pydantic I/O models
│   ├── ingestion/
│   │   ├── edgar.py         ← SEC EDGAR 10-K fetch
│   │   ├── chunker.py       ← paragraph-aware splitter
│   │   └── xbrl.py          ← XBRL financial facts + YoY trend
│   ├── rag/
│   │   ├── embedder.py      ← fastembed wrapper
│   │   ├── retriever.py     ← Qdrant client
│   │   └── pipeline.py      ← ingest + retrieve
│   ├── services/
│   │   ├── llm.py           ← multi-provider router + model selector + cost recording
│   │   ├── dashboard.py     ← XBRL + LLM extraction, Redis cache
│   │   ├── report.py        ← 10-K fundamental analysis report, 24h cache
│   │   └── comparison.py    ← two-ticker analysis
│   ├── cache/
│   │   ├── redis_client.py
│   │   ├── ticker_cache.py
│   │   ├── filing_registry.py  ← filing-type aware keys (10-K, 10-Q, 8-K ready)
│   │   └── cost_tracker.py     ← LLM cost recording + day/week/month aggregation
│   └── jobs/refresh_tickers.py
├── frontend/
│   └── src/
│       ├── App.jsx
│       └── components/
│           ├── CompanySearch.jsx   ← debounced autocomplete
│           ├── FilingPanel.jsx     ← chat panel + 8-model selector
│           ├── Dashboard.jsx       ← metrics + TradingView chart
│           ├── ReportView.jsx      ← 10-K analysis report (findings, risk gauge, bull/bear)
│           ├── CompareView.jsx     ← comparison + YoY revenue trend + compact reports
│           ├── CostPanel.jsx       ← LLM cost modal (day/week/month, per-model table)
│           └── StatusDots.jsx      ← Redis/Qdrant health indicators
└── tests/
    ├── conftest.py
    └── test_routes.py
```

---

## Roadmap

- [x] SEC EDGAR 10-K ingestion + RAG pipeline
- [x] XBRL financial data parsing (deterministic metrics)
- [x] Multi-provider LLM routing (DeepSeek / Claude / OpenAI)
- [x] Per-request model selector UI
- [x] YoY revenue comparison
- [x] Redis + Qdrant health monitoring
- [x] Rotating file logger + per-endpoint structured logging
- [x] Unit tests — backend (pytest) + frontend (vitest)
- [x] 10-K fundamental analysis report (findings table, risk gauge, bull/bear, verdict)
- [x] Filing-type aware Redis key schema (ready for 10-Q / 8-K)
- [x] LLM cost tracker — per-call recording, day/week/month aggregation, UI panel
- [ ] Hybrid BM25 + dense vector search
- [ ] YoY risk factor diff (highlight what changed year-over-year)
- [ ] FinBERT sentiment analysis per MD&A section
- [ ] Multi-filing RAG (query across 3+ years) + LangGraph
- [ ] LangFuse tracing — cost and latency dashboard
- [ ] RAGAS evaluation baseline
- [ ] GCP Cloud Run deployment
