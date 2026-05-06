# FinSight AI

**Financial Risk Intelligence Platform** — ingests SEC EDGAR 10-K, 10-Q, and 8-K filings, stores them as vector embeddings, and delivers multi-tab AI-powered analysis grounded in source documents.

Built as a portfolio project demonstrating production-grade AI engineering: multi-filing RAG pipeline, Celery background ingestion, deterministic XBRL financial parsing, multi-provider LLM routing, and a fully reactive analyst UI.

---

## Features

| Feature | Detail |
|---------|--------|
| **Multi-Filing Ingest** | Fetches 10-K (×2), 10-Q (×4), 8-K (×10) from SEC EDGAR. Chunks, embeds with BGE-base, stores in Qdrant. Idempotent — re-ingesting is a no-op unless `?force=true` |
| **Celery Background Tasks** | Ingestion runs in a Celery worker. Frontend polls task status with live progress steps. Report is pre-generated during the task — Fundamentals tab loads instantly after ingest |
| **8-K Event Classification** | Classifies 8-K filings by EDGAR item number (`2.02` → Earnings, `5.02` → Leadership Change, etc.) — deterministic, zero LLM cost |
| **RAG Q&A** | Semantic search over filing chunks → grounded LLM answer with citations and cost metadata. Supports cross-filing retrieval (10-K + 10-Q simultaneously via Qdrant MatchAny) |
| **XBRL Financials** | Revenue, net income, gross margin, YoY growth pulled directly from SEC EDGAR XBRL API — deterministic, no LLM guessing |
| **6-Tab Analyst Sidebar** | Fundamentals, News, Sentiment, Risk, Technical, Bull vs Bear. Each tab shows a pulsing loader while fetching, green checkmark when done |
| **Fundamentals Tab** | Full 10-K report: findings table (revenue / profitability / risk / sentiment), risk gauge (0–100), management outlook, executive summary. Cached 24h |
| **Risk Tab** | Risk score gauge, risk factor bullets, 8-K event feed, YoY risk diff (new / escalated / resolved) |
| **Sentiment Tab** | Management sentiment score, section breakdown, key themes from MD&A |
| **Bull vs Bear Tab** | LLM-generated investment debate transcript: 4-turn bull/bear exchange with summary bullets |
| **YoY Risk Diff** | Compares two years of risk factor text, surfaces what is new, escalated, or resolved |
| **Side-by-side Compare** | Two-ticker head-to-head: financial bar charts, YoY revenue trend, compact analysis for both |
| **TradingView Charts** | Symbol Overview (area chart, built-in date ranges) as default. Toggle to full Advanced chart with indicators |
| **Smart Model Router** | Auto-routes simple queries to cheap model, complex reasoning to power model. Every call logs model, tokens, and cost |
| **LLM Cost Tracker** | Atomic Redis cost recording per call. Aggregates day/week/month with per-model breakdown. `$` button in topbar |
| **Model Selector** | Choose DeepSeek Chat/Reasoner, Claude Haiku/Sonnet/Opus, or GPT-4o per request |
| **Company Search** | Autocomplete across ~13k SEC-registered companies via Redis Hash — zero API calls at query time |
| **Health Monitoring** | Redis + Qdrant status indicators in the topbar, polling every 30s |

---

## Architecture

```
React (Vite) :3000
      │
      ▼
FastAPI :8000  ──  APScheduler (daily 02:00 UTC ticker refresh)
      │
      ├── api/routes.py           ← REST endpoints, Pydantic I/O, per-request logging
      │
      ├── ingestion/
      │     edgar.py              ← SEC EDGAR API → 10-K / 10-Q / 8-K fetch
      │     chunker.py            ← paragraph-aware chunking (1000 char / 200 overlap)
      │     xbrl.py               ← XBRL financial facts (revenue, income, margin, YoY)
      │     sections.py           ← 10-K section extractor (Item 1, 1A, 7, 8)
      │
      ├── rag/
      │     embedder.py           ← fastembed + BAAI/bge-base-en-v1.5 (ONNX, CPU)
      │     retriever.py          ← Qdrant upsert + query with filing_id / MatchAny filter
      │     pipeline.py           ← ingest() / retrieve() / retrieve_multi() orchestration
      │
      ├── services/
      │     edgar_pipeline.py     ← deterministic multi-filing pipeline, 8-K classifier
      │     llm.py                ← DeepSeek → Anthropic → OpenAI → mock fallback chain
      │     dashboard.py          ← XBRL metrics + LLM narrative, Redis 7d cache
      │     report.py             ← fundamental analysis: findings, risk, bull/bear, debate
      │     diff.py               ← YoY risk factor diff (new / escalated / resolved)
      │     comparison.py         ← two-ticker LLM analysis, Redis cache
      │
      ├── tasks/
      │     edgar_tasks.py        ← Celery task: ingest → dashboard → pre-generate report
      │
      └── cache/
            ticker_cache.py       ← SEC ticker → CIK, Redis Hash (DB 0)
            filing_registry.py    ← filing-type aware registry keys
            cost_tracker.py       ← per-call cost recording, day/week/month aggregation
            redis_client.py       ← Redis singleton
      │
      ▼              ▼              ▼             ▼
  Qdrant :6333   Redis DB0      Redis DB1     Flower :5555
  (vectors)      (app data)     (Celery)      (task monitor)
```

**LLM routing (auto, overridable per-request):**

| Query type | Default model | Cost / 1M tokens |
|------------|---------------|-----------------|
| Simple fact lookup | `deepseek-chat` | $0.07 in / $0.28 out |
| Complex reasoning, "analyse", "compare", "why" | `claude-sonnet-4-6` | varies |
| User override | Any of 8 models | — |

**Fallback chain:** DeepSeek → Anthropic Claude → OpenAI → mock response (app never crashes on missing keys)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI 0.110+, Pydantic v2, uvicorn |
| Embeddings | fastembed 0.3.6 + `BAAI/bge-base-en-v1.5` (ONNX, CPU, no torch, 768-dim) |
| Vector DB | Qdrant 1.9+ (cosine similarity, per-filing and cross-filing MatchAny filters) |
| LLM | DeepSeek (primary) · Anthropic Claude · OpenAI (all switchable per-request) |
| Financial Data | SEC EDGAR XBRL API (deterministic, no LLM extraction) |
| Cache | Redis 8 — DB 0: app data (ticker index, reports, 8-K events) · DB 1: Celery broker/backend |
| Background Tasks | Celery 5 + Flower (task monitoring dashboard at :5555) |
| Scheduler | APScheduler 3.10 (daily ticker refresh at 02:00 UTC) |
| Ingestion | SEC EDGAR REST API via httpx (rate-limited: 0.12s delay = 8 req/s, within SEC's 10 req/s limit) |
| Frontend | React 19 + Vite, TradingView Widgets, Lucide icons |
| Containers | Docker + Docker Compose (backend, frontend, qdrant, redis, celery-worker, flower) |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/companies/{ticker}/ingest` | Queue Celery task: fetch + embed 10-K/10-Q/8-K. Returns `task_id` |
| `GET` | `/api/companies/{ticker}/ingest/status` | Poll Celery task status + live progress step message |
| `POST` | `/api/chat` | RAG Q&A with optional `model` override |
| `GET` | `/api/companies/search?q=apple` | Company autocomplete from Redis (~13k companies) |
| `GET` | `/api/companies/{ticker}/dashboard` | XBRL metrics + LLM narrative |
| `GET` | `/api/companies/{ticker}/report` | Full fundamental analysis report. Add `?refresh=true` to regenerate |
| `GET` | `/api/companies/{ticker}/diff` | YoY risk factor diff (new / escalated / resolved) |
| `GET` | `/api/companies/{ticker}/events` | Recent 8-K events from Redis (classified by EDGAR item number) |
| `POST` | `/api/companies/compare` | Head-to-head comparison with YoY revenue trend |
| `GET` | `/api/admin/costs` | LLM cost breakdown by day/week/month, per model |
| `POST` | `/api/admin/refresh-tickers` | Manually refresh ticker cache |
| `GET` | `/api/health` | Redis + Qdrant status + filing count |
| `GET` | `/docs` | Swagger UI |

### Example: Ingest + Query

```bash
# Ingest Apple's 10-K, 10-Q, and 8-K filings (runs in background)
curl -X POST http://localhost:8000/api/companies/AAPL/ingest

# Poll Celery task status
curl http://localhost:8000/api/companies/AAPL/ingest/status

# Ask a question grounded in the filings
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "question": "What are the main risk factors?"}'

# Ask with a specific model
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "question": "Analyse revenue trends", "model": "claude-sonnet-4-6"}'

# Get recent 8-K events (earnings, leadership changes, M&A)
curl http://localhost:8000/api/companies/AAPL/events

# YoY risk diff — what changed year-over-year
curl http://localhost:8000/api/companies/AAPL/diff

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
| Flower (Celery monitor) | http://localhost:5555 |

### Local (no Docker)

```bash
# Backend
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Celery worker (separate terminal)
cd backend && celery -A celery_app worker --loglevel=info --concurrency=1

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
# LLM providers — DeepSeek is primary (~10x cheaper than Claude Haiku)
DEEPSEEK_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...   # optional fallback
OPENAI_API_KEY=sk-...          # optional fallback

# Infrastructure — defaults match docker-compose
QDRANT_URL=http://qdrant:6333
REDIS_URL=redis://redis:6379

# Reserved (not yet wired)
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
```

---

## Repo Structure

```
finsight-ai/
├── docker-compose.yml
├── pytest.ini
├── FEATURES.md                   ← full feature backlog with implementation plans
├── backend/
│   ├── main.py                   ← FastAPI entry, lifespan, request logging middleware
│   ├── config.py                 ← Pydantic Settings
│   ├── celery_app.py             ← Celery config (Redis DB 1, task routing)
│   ├── logging_config.py         ← rotating file logger (10MB × 5 backups)
│   ├── requirements.txt
│   ├── api/routes.py             ← all endpoints
│   ├── models/schemas.py         ← Pydantic I/O models
│   ├── ingestion/
│   │   ├── edgar.py              ← SEC EDGAR 10-K / 10-Q / 8-K fetch
│   │   ├── chunker.py            ← paragraph-aware splitter (1000 char / 200 overlap)
│   │   ├── sections.py           ← 10-K section extractor (Item 1, 1A, 7, 8)
│   │   └── xbrl.py               ← XBRL financial facts + YoY trend
│   ├── rag/
│   │   ├── embedder.py           ← fastembed wrapper (BGE-base, ONNX, CPU)
│   │   ├── retriever.py          ← Qdrant client (upsert, query, MatchAny cross-filing)
│   │   └── pipeline.py           ← ingest / retrieve / retrieve_multi
│   ├── services/
│   │   ├── edgar_pipeline.py     ← deterministic multi-filing pipeline + 8-K classifier
│   │   ├── llm.py                ← DeepSeek → Anthropic → OpenAI → mock chain
│   │   ├── dashboard.py          ← XBRL + LLM extraction, Redis 7d cache
│   │   ├── report.py             ← analysis: findings, risk gauge, bull/bear, debate transcript
│   │   ├── diff.py               ← YoY risk factor diff
│   │   ├── comparison.py         ← two-ticker LLM analysis
│   │   └── store.py              ← shared data store helpers
│   ├── tasks/
│   │   └── edgar_tasks.py        ← Celery task: ingest → dashboard → pre-generate report
│   ├── cache/
│   │   ├── redis_client.py
│   │   ├── ticker_cache.py       ← ~13k company Redis Hash, 2am daily refresh
│   │   ├── filing_registry.py    ← filing-type aware registry keys
│   │   └── cost_tracker.py       ← per-call cost recording, aggregation
│   └── jobs/refresh_tickers.py
├── frontend/
│   └── src/
│       ├── App.jsx                    ← routing, polling, tab status state
│       └── components/
│           ├── LandingPage.jsx        ← fullscreen company search entry point
│           ├── CompanySearch.jsx      ← debounced autocomplete (landing + topbar variants)
│           ├── AnalystSidebar.jsx     ← 6-tab sidebar with per-tab status dot indicators
│           ├── Dashboard.jsx          ← XBRL metrics + chart + Celery progress steps
│           ├── StockChart.jsx         ← TradingView Symbol Overview (area chart)
│           ├── FilingPanel.jsx        ← chat panel + 8-model selector
│           ├── ReportView.jsx         ← 10-K analysis report (findings, risk gauge, bull/bear)
│           ├── CompareView.jsx        ← comparison + YoY revenue trend + compact reports
│           ├── CostPanel.jsx          ← LLM cost modal (day/week/month, per-model table)
│           ├── StatusDots.jsx         ← Redis/Qdrant health indicators
│           └── tabs/
│               ├── RiskTab.jsx        ← risk gauge, risk factors, 8-K events, YoY diff
│               ├── SentimentTab.jsx   ← sentiment score, section breakdown, MD&A themes
│               ├── BullBearTab.jsx    ← bull/bear bullets + LLM 4-turn debate transcript
│               ├── TechnicalTab.jsx   ← (placeholder — technical indicators)
│               └── NewsTab.jsx        ← (placeholder — news feed)
└── tests/
    ├── conftest.py
    ├── test_routes.py
    └── eval_baseline/
        └── questions.json            ← 10 hand-curated RAG Q&A pairs for RAGAS eval
```

---

## Roadmap

- [x] SEC EDGAR 10-K ingestion + RAG pipeline
- [x] 10-Q and 8-K ingestion (multi-filing, cross-filing retrieval)
- [x] 8-K event classification via EDGAR item numbers (deterministic, zero LLM cost)
- [x] Celery background ingestion with live progress polling
- [x] Report pre-generation during ingest (Fundamentals tab loads instantly)
- [x] XBRL financial data parsing (deterministic metrics, no LLM extraction)
- [x] Multi-provider LLM routing with graceful degradation (DeepSeek → Claude → OpenAI → mock)
- [x] Per-request model selector UI (8 models)
- [x] LLM cost tracker — per-call recording, day/week/month aggregation, UI panel
- [x] YoY revenue comparison + YoY risk factor diff
- [x] LLM-generated bull/bear debate transcript
- [x] 6-tab analyst sidebar with per-tab loading status indicators
- [x] TradingView Symbol Overview chart (default) + Advanced chart toggle
- [x] Landing page with fullscreen company search
- [x] Redis + Qdrant health monitoring
- [x] Rotating file logger + per-endpoint structured logging
- [x] Unit tests — backend (pytest) + frontend (vitest)
- [x] RAGAS eval baseline (10 hand-curated Q&A pairs)
- [ ] Hybrid BM25 + dense vector search (RRF fusion)
- [ ] FinBERT sentiment analysis per MD&A section
- [ ] Technical tab — RSI, MACD, moving averages
- [ ] News tab — company news feed
- [ ] CrewAI analyst crew (Researcher + Analyst + Report Writer agents)
- [ ] EDGAR MCP server via FastMCP (Claude Desktop / Ruflo compatible)
- [ ] LangFuse tracing — cost and latency observability
- [ ] GCP Cloud Run deployment
