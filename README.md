# FinSight AI

**Financial Risk Intelligence Platform** — ingests SEC EDGAR 10-K, 10-Q, and 8-K filings, stores them as hybrid vector embeddings, and delivers multi-tab AI-powered fundamental analysis grounded in source documents.

Built as a portfolio project demonstrating production-grade AI engineering: multi-filing RAG pipeline with cross-encoder reranking, Celery background ingestion, deterministic XBRL financial parsing, FinBERT sentiment analysis, multi-provider LLM routing with cost tracking, rate limiting, and a fully reactive analyst UI.

---

## What It Does

Search any SEC-registered company → FinSight fetches its latest filings from EDGAR, embeds them into a hybrid vector store, and generates a comprehensive equity research report in the style of a professional analyst note — with risk scoring, sentiment analysis, YoY risk diff, technical indicators, and a bull/bear debate transcript.

---

## Features

### Data Ingestion
| Feature | Detail |
|---------|--------|
| **SEC EDGAR Multi-Filing** | Fetches 10-K (×2 years), 10-Q (×4 quarters), 8-K (×10 recent) per company. Rate-limited at 0.12s between requests (8 req/s, within SEC's 10 req/s limit) |
| **Celery Background Tasks** | Ingestion runs in a Celery worker. Frontend polls task status every 3s with live progress messages. Report is pre-generated during ingest — Fundamentals tab loads instantly |
| **8-K Event Classification** | Classifies 8-K filings by EDGAR item number (`2.02` → Earnings, `5.02` → Leadership Change, `1.01` → Acquisition, etc.) — deterministic, zero LLM cost |
| **XBRL Financial Parser** | Revenue, net income, gross margin, YoY growth pulled directly from SEC EDGAR XBRL API — exact numbers, no LLM extraction |
| **Paragraph-Aware Chunker** | 1000-char chunks with 200-char overlap across 10-K sections. Preserves paragraph boundaries to prevent context loss at chunk edges |

### RAG Pipeline
| Feature | Detail |
|---------|--------|
| **BGE Embeddings** | `BAAI/bge-base-en-v1.5` via fastembed (ONNX, CPU-only, 768-dim). No PyTorch, no GPU. Matches OpenAI ada-002 quality at zero API cost |
| **Hybrid Search** | Dense (cosine) + sparse (BM25/IDF) vectors in Qdrant, fused with Reciprocal Rank Fusion (RRF). Exact financial jargon (BM25) + semantic meaning (dense) |
| **Cross-Encoder Reranker** | `BAAI/bge-reranker-base` (280MB ONNX, CPU) rescores top-20 RRF candidates for true relevance. Catches cases where similarity ≠ relevance — e.g. "supply chain risks" → "Geographic Concentration Risk" section |
| **Cross-Filing Retrieval** | RAG search across 10-K + 10-Q simultaneously via Qdrant `MatchAny` filter. Enables quarterly trend questions over annual filings |
| **Multi-Query Retrieval** | Chat endpoint issues both the original question and section-targeted rephrasing to improve recall on topic-specific queries |

### AI Analysis
| Feature | Detail |
|---------|--------|
| **Comprehensive Analysis Report** | Full equity research note: findings table (Revenue / Profitability / Risk / Sentiment with signal badges), risk score gauge (0–100), trend narrative, management themes, bull/bear case bullets, verdict. Cached 24h in Redis |
| **FinBERT Sentiment** | `ProsusAI/finbert` runs locally on CPU — zero API cost. Scores MD&A (Item 7) chunks: positive / negative / neutral. Aggregates to continuous scalar `(avg_pos - avg_neg + 1) / 2`. Filters boilerplate before inference |
| **YoY Risk Factor Diff** | Compares Item 1A text between current and prior year 10-K using `difflib` + BGE semantic matching. Classifies paragraphs as new / changed / removed / unchanged. Handles rewording that isn't a real change |
| **Bull/Bear Debate** | LLM-simulated 4-turn investment debate grounded in filing data. Placeholder for CrewAI multi-agent debate (Feature 3c) |
| **Technical Analysis** | yfinance fetches 1-year daily OHLCV. Computes RSI(14), MACD(12,26,9), SMA50, SMA200, Bollinger Bands (20,2), Volume ratio. LLM generates verdict. TradingView Technical Analysis widget alongside |
| **Company News** | Finnhub API — recent headlines with FinBERT sentiment per article. 1hr Redis cache |

### LLM Infrastructure
| Feature | Detail |
|---------|--------|
| **Multi-Provider Routing** | DeepSeek (primary, cheapest) → Anthropic Claude → OpenAI → mock response. App never crashes on missing keys |
| **Smart Model Router** | Auto-routes simple queries to cheap model (`deepseek-chat`), complex reasoning to power model. Keywords like "analyse", "compare", "why" + queries >200 chars trigger the reasoning model |
| **Per-Request Model Override** | 8-model pill selector in the chat panel. Choose DeepSeek Chat/Reasoner, Claude Haiku/Sonnet/Opus, or GPT-4o per query |
| **LLM Cost Tracker** | Atomic Redis cost recording per call with model, tokens_in, tokens_out, cost_usd, latency_ms. Aggregates day/week/month with per-model breakdown. `$` button in topbar |
| **JSON Repair** | `json-repair` library + 3-attempt retry for malformed LLM JSON output. Logs which attempt succeeded for prompt quality monitoring |

### Production Hardening
| Feature | Detail |
|---------|--------|
| **Rate Limiting** | `slowapi` backed by Redis (shared across Uvicorn workers). Per-endpoint limits: ingest 5/min, diff 5/min, sentiment 5/min, report 10/min, compare 10/min, technicals 20/min, news 20/min, dashboard 30/min, search 60/min. Returns 429 + Retry-After |
| **Structured Logging** | Three rotating log files: `finsight.log` (all), `llm.log` (LLM calls only), `tasks.log` (Celery). 10MB × 5 backups each. Named loggers with propagation |
| **Langfuse Tracing** | Full `@observe` instrumentation across every LLM call, RAG retrieval, ingest, report generation, and debate. Nested span hierarchy: `report-lookup → report-generate → retrieve-multi × 5 → call-llm-raw + debate`. Chat traces tagged with `user_id=ticker`, `tags=["chat"]`. Cache hits visible. No-op when keys absent |
| **Redis TTL Strategy** | Different TTLs per data type: sentiment 30d, diff 30d, report 24h, dashboard 7d, news 1hr, technicals 1hr. Matches how often data actually changes |
| **Session Persistence** | Last selected company persists across browser refresh via localStorage. Restore is two fast Redis reads — no pipeline re-execution |
| **Graceful Degradation** | Every LLM call has a mock fallback. Reranker falls back to RRF order on failure. News failures don't block the report |

### Frontend
| Feature | Detail |
|---------|--------|
| **6-Tab Analyst Sidebar** | Fundamentals · News · Sentiment · Risk · Technical · Bull vs Bear. Each tab shows pulsing loader while fetching, status indicator when done |
| **Comprehensive Report View** | Company overview, findings table with signal badges (✅ ⚠️ 🔴 ℹ️), financial trend narrative, risk gauge + sentiment badge side-by-side, top risk factors, management themes, colour-coded verdict |
| **Risk Tab** | Risk score gauge, top risk factor bullets, 8-K event feed, YoY diff (new/changed/removed paragraphs) |
| **Sentiment Tab** | FinBERT score with breakdown (positive/negative/neutral class probabilities), most polarised MD&A sentences |
| **Technical Tab** | Computed indicators table (RSI, MACD, SMA50/200, Bollinger Bands, Volume), AI verdict paragraph, signal breakdown (buy/neutral/sell counts), TradingView Technical Analysis widget |
| **Bull vs Bear Tab** | Bull case bullets, Bear case bullets, 4-turn LLM debate transcript |
| **News Tab** | Finnhub headlines with FinBERT sentiment badge per article |
| **Compare View** | Single overlay chart (% normalised, both tickers on one canvas), risk score + sentiment side-by-side, financial metrics bar chart, YoY revenue trend, LLM head-to-head analysis, compact reports for both tickers |
| **TradingView Integration** | StockChart (Symbol Overview, area line, date ranges). CompareOverlayChart (two tickers overlaid, percentage scale). Technical Analysis widget. All theme-aware — rebuild on dark/light toggle via MutationObserver |
| **Company Search** | Debounced autocomplete across ~13k SEC-registered companies via Redis Hash — zero API calls at query time. O(1) by ticker, O(n) by name (2-5ms in RAM) |
| **Health Monitoring** | Redis + Qdrant status dots in topbar, polling every 30s |
| **Dark / Light Theme** | Auto-switches at 19:00/07:00. Manual override persists in localStorage |

---

## Architecture

```
React (Vite) :3000
      │
      ▼
FastAPI :8000  ──  slowapi (Redis rate limiter)  ──  APScheduler (02:00 UTC ticker refresh)
      │
      ├── api/routes.py              ← REST endpoints, rate-limited, Pydantic I/O
      │
      ├── ingestion/
      │     edgar.py                 ← SEC EDGAR 10-K / 10-Q / 8-K (rate-limited 0.12s)
      │     chunker.py               ← paragraph-aware chunking (1000 char / 200 overlap)
      │     xbrl.py                  ← XBRL financial facts (revenue, income, margin, YoY)
      │     sections.py              ← 10-K section extractor (Item 1, 1A, 7, 8)
      │     news.py                  ← Finnhub news + FinBERT sentiment per article
      │
      ├── rag/
      │     embedder.py              ← fastembed + BAAI/bge-base-en-v1.5 (ONNX, CPU, 768-dim)
      │     retriever.py             ← Qdrant hybrid search (dense + sparse, RRF fusion)
      │     pipeline.py              ← ingest / retrieve / retrieve_multi (with reranking)
      │     reranker.py              ← BAAI/bge-reranker-base cross-encoder (ONNX, CPU)
      │
      ├── services/
      │     edgar_pipeline.py        ← multi-filing pipeline + deterministic 8-K classifier
      │     llm.py                   ← DeepSeek → Anthropic → OpenAI → mock fallback chain
      │     observability.py         ← Langfuse init + flush, @observe across all LLM/RAG calls
      │     dashboard.py             ← XBRL metrics + LLM narrative, Redis 7d cache
      │     report.py                ← analysis report: findings, risk, bull/bear, debate
      │     diff.py                  ← YoY risk factor diff (difflib + BGE semantic matching)
      │     comparison.py            ← two-ticker LLM analysis, Redis cache
      │     sentiment.py             ← FinBERT on Item 7 chunks (CPU, 30d Redis cache)
      │     technical.py             ← yfinance OHLCV → RSI/MACD/SMA/BB/Vol + LLM verdict
      │
      ├── tasks/
      │     edgar_tasks.py           ← Celery: ingest → embed → classify → pre-gen report
      │
      ├── cache/
      │     ticker_cache.py          ← 13k company Redis Hash, 2am daily refresh
      │     filing_registry.py       ← filing-type aware ingestion gate
      │     cost_tracker.py          ← per-call cost log, day/week/month aggregation
      │     redis_client.py          ← Redis singleton
      │
      └── limiter.py                 ← slowapi limiter (Redis-backed, shared across workers)
      │
      ▼              ▼              ▼             ▼
  Qdrant :6333   Redis DB0      Redis DB1     Flower :5555
  (vectors)      (app data)     (Celery)      (task monitor)
```

### RAG Retrieval Pipeline

```
User query
    ↓
BGE embed (query) + sparse encode
    ↓
Qdrant hybrid search — top 20 candidates
  ├── Dense branch: cosine similarity (BAAI/bge-base-en-v1.5)
  └── Sparse branch: BM25/IDF (exact financial term matching)
    ↓
Reciprocal Rank Fusion (RRF) — merges dense + sparse ranked lists
    ↓
BGE reranker (BAAI/bge-reranker-base) — reads query + chunk together, scores relevance
    ↓
Top 5 chunks by reranker score → LLM context
```

### LLM Routing

| Query type | Model | Cost / 1M tokens |
|------------|-------|-----------------|
| Simple fact lookup | `deepseek-v4-flash` | $0.14 in / $0.28 out |
| Complex: "analyse", "compare", "why", >200 chars | `deepseek-v4-pro` | $0.44 in / $0.87 out |
| User override | Any of 8 models | varies |

**Fallback chain:** DeepSeek → Anthropic Claude → OpenAI → mock response

### Rate Limits

| Endpoint | Limit | Reason |
|----------|-------|--------|
| `/ingest`, `/diff`, `/sentiment` | 5/min | Heavy pipeline / CPU inference |
| `/report`, `/compare` | 10/min | LLM call ~$0.02–0.05 |
| `/technicals`, `/news` | 20/min | External API + LLM |
| `/dashboard` | 30/min | Usually Redis-cached |
| `/search`, `/health` | 60/min | Pure Redis lookup |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI 0.110+, Pydantic v2, uvicorn, slowapi (rate limiting) |
| Embeddings | fastembed 0.3.6 + `BAAI/bge-base-en-v1.5` (ONNX, CPU, 768-dim) |
| Reranker | `BAAI/bge-reranker-base` via fastembed (ONNX, CPU, 280MB) |
| Vector DB | Qdrant 1.9+ — dense + sparse hybrid, RRF fusion, filing-scoped filters |
| Sentiment | `ProsusAI/finbert` via HuggingFace transformers (CPU, 110M params) |
| LLM | DeepSeek (primary) · Anthropic Claude · OpenAI (switchable per-request) |
| Observability | Langfuse 3 — `@observe` tracing, nested spans, cost + latency per call |
| Financial Data | SEC EDGAR XBRL API (deterministic) · yfinance (technical indicators) |
| News | Finnhub API |
| Cache | Redis 8 — DB 0: app data · DB 1: Celery broker/backend |
| Background Tasks | Celery 5 + Flower (monitoring at :5555) |
| Scheduler | APScheduler 3.10 (daily 02:00 UTC ticker refresh) |
| JSON Reliability | json-repair + 3-attempt retry for malformed LLM output |
| Frontend | React 19 + Vite, TradingView Widgets, Lucide icons |
| Containers | Docker + Docker Compose (6 services) |

---

## API Endpoints

| Method | Path | Rate Limit | Description |
|--------|------|-----------|-------------|
| `POST` | `/api/companies/{ticker}/ingest` | 5/min | Queue Celery ingest task. Returns `task_id` |
| `GET` | `/api/companies/{ticker}/ingest/status` | — | Poll Celery task status + progress step |
| `GET` | `/api/companies/{ticker}/report` | 10/min | Full analysis report. `?refresh=true` to regenerate |
| `GET` | `/api/companies/{ticker}/dashboard` | 30/min | XBRL metrics + LLM narrative |
| `GET` | `/api/companies/{ticker}/diff` | 5/min | YoY risk factor diff (new/changed/removed) |
| `GET` | `/api/companies/{ticker}/sentiment` | 5/min | FinBERT MD&A sentiment score |
| `GET` | `/api/companies/{ticker}/technicals` | 20/min | RSI, MACD, SMA50/200, Bollinger Bands + LLM verdict |
| `GET` | `/api/companies/{ticker}/news` | 20/min | Finnhub headlines + FinBERT sentiment |
| `GET` | `/api/companies/{ticker}/events` | — | Recent 8-K events classified by type |
| `POST` | `/api/companies/compare` | 10/min | Two-ticker head-to-head with YoY revenue trend |
| `POST` | `/api/chat` | — | RAG Q&A with optional model override |
| `GET` | `/api/companies/search?q=apple` | 60/min | Company autocomplete from Redis |
| `GET` | `/api/admin/costs` | — | LLM cost breakdown day/week/month per model |
| `POST` | `/api/admin/refresh-tickers` | — | Manually refresh ticker cache |
| `GET` | `/api/health` | 60/min | Redis + Qdrant status + filing count |
| `GET` | `/docs` | — | Swagger UI |

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
# Backend (pytest)
pip install -r backend/requirements-test.txt
pytest

# Frontend (vitest)
cd frontend && npm install && npm test
```

---

## Environment Variables

```env
# LLM providers — DeepSeek is primary (~10x cheaper than Claude Haiku)
DEEPSEEK_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...   # optional fallback
OPENAI_API_KEY=sk-...          # optional fallback

# News
FINNHUB_API_KEY=...

# Infrastructure — defaults match docker-compose
QDRANT_URL=http://qdrant:6333
REDIS_URL=redis://redis:6379

# Observability — get keys from Langfuse UI → Settings → API Keys
# Tracing is a no-op when these are absent (safe to omit in dev)
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com   # EU cloud; use https://us.cloud.langfuse.com for US
```

---

## Repo Structure

```
finsight-ai/
├── docker-compose.yml
├── pytest.ini
├── LICENSE
├── FEATURES.md                        ← full feature backlog with implementation plans
├── backend/
│   ├── main.py                        ← FastAPI app, lifespan, rate limiter, middleware
│   ├── config.py                      ← Pydantic Settings (all env vars)
│   ├── limiter.py                     ← slowapi rate limiter (Redis-backed singleton)
│   ├── celery_app.py                  ← Celery config (Redis DB 1)
│   ├── logging_config.py              ← 3 rotating log files (finsight, llm, tasks)
│   ├── requirements.txt
│   ├── api/routes.py                  ← all endpoints with rate limit decorators
│   ├── models/schemas.py              ← Pydantic I/O models (AnalysisReport, FindingRow…)
│   ├── ingestion/
│   │   ├── edgar.py                   ← SEC EDGAR fetch (rate-limited 0.12s)
│   │   ├── chunker.py                 ← paragraph-aware splitter
│   │   ├── sections.py                ← 10-K section extractor (Item 1/1A/7/8)
│   │   ├── xbrl.py                    ← XBRL financials + YoY trend
│   │   └── news.py                    ← Finnhub news + FinBERT per article
│   ├── rag/
│   │   ├── embedder.py                ← fastembed BGE wrapper
│   │   ├── retriever.py               ← Qdrant hybrid search (dense + sparse, RRF)
│   │   ├── pipeline.py                ← ingest / retrieve / retrieve_multi + reranking
│   │   └── reranker.py                ← BGE cross-encoder reranker (ONNX, CPU)
│   ├── services/
│   │   ├── edgar_pipeline.py          ← multi-filing pipeline + 8-K classifier
│   │   ├── llm.py                     ← DeepSeek → Claude → OpenAI → mock chain
│   │   ├── observability.py           ← Langfuse init + flush (called at lifespan)
│   │   ├── dashboard.py               ← XBRL + LLM, Redis 7d cache
│   │   ├── report.py                  ← analysis report + JSON repair + 3-attempt retry
│   │   ├── diff.py                    ← YoY risk factor diff
│   │   ├── comparison.py              ← two-ticker LLM analysis
│   │   ├── sentiment.py               ← FinBERT on Item 7, Redis 30d cache
│   │   ├── technical.py               ← yfinance + pandas indicators + LLM verdict
│   │   └── store.py                   ← shared data store helpers
│   ├── tasks/edgar_tasks.py           ← Celery: ingest → embed → classify → report
│   ├── cache/
│   │   ├── redis_client.py
│   │   ├── ticker_cache.py            ← 13k companies, 2am refresh
│   │   ├── filing_registry.py         ← filing-type registry
│   │   └── cost_tracker.py            ← per-call cost recording + aggregation
│   └── jobs/refresh_tickers.py
├── frontend/
│   └── src/
│       ├── App.jsx                    ← routing, ingest polling, localStorage persistence
│       └── components/
│           ├── LandingPage.jsx        ← fullscreen search entry point
│           ├── CompanySearch.jsx      ← debounced Redis autocomplete
│           ├── AnalystSidebar.jsx     ← 6-tab sidebar with status dots
│           ├── Dashboard.jsx          ← XBRL metrics + Celery progress steps
│           ├── StockChart.jsx         ← TradingView Symbol Overview (theme-aware)
│           ├── ReportView.jsx         ← analysis report (findings, risk gauge, verdict)
│           ├── CompareView.jsx        ← overlay chart + risk/sentiment + reports
│           ├── FilingPanel.jsx        ← RAG chat + 8-model selector
│           ├── CostPanel.jsx          ← LLM cost modal
│           ├── StatusDots.jsx         ← Redis/Qdrant health indicators
│           └── tabs/
│               ├── RiskTab.jsx        ← risk gauge, factors, 8-K events, YoY diff
│               ├── SentimentTab.jsx   ← FinBERT score, breakdown, sentences
│               ├── BullBearTab.jsx    ← bull/bear bullets + debate transcript
│               ├── TechnicalTab.jsx   ← computed indicators + LLM verdict + TV widget
│               └── NewsTab.jsx        ← Finnhub headlines + sentiment badges
└── tests/
    ├── conftest.py
    ├── test_routes.py
    └── eval_baseline/questions.json   ← 10 hand-curated RAG Q&A pairs (RAGAS)
```

---

## Roadmap

### Completed
- [x] SEC EDGAR 10-K, 10-Q, 8-K ingestion with rate limiting
- [x] 8-K event classification (deterministic, zero LLM cost)
- [x] Celery background ingestion with live progress polling
- [x] Report pre-generation during ingest (instant tab load)
- [x] XBRL financial data (deterministic metrics, no LLM)
- [x] BGE-base embeddings (ONNX, CPU, no torch, no GPU)
- [x] Qdrant hybrid search — BM25 + dense vectors, RRF fusion
- [x] Cross-encoder reranker (BAAI/bge-reranker-base, CPU)
- [x] Multi-provider LLM routing with graceful degradation
- [x] Smart model router (cheap → power by query complexity)
- [x] Per-request model selector (8 models)
- [x] LLM cost tracker (per-call, day/week/month aggregation)
- [x] JSON repair + 3-attempt retry for LLM reliability
- [x] Rate limiting (slowapi, Redis-backed, per-endpoint)
- [x] FinBERT sentiment on MD&A (CPU, boilerplate-filtered)
- [x] YoY risk factor diff (difflib + BGE semantic matching)
- [x] Comprehensive analysis report (findings table, risk gauge, bull/bear, verdict)
- [x] Technical analysis (yfinance, RSI/MACD/SMA50/200/BB/Volume + LLM verdict)
- [x] Finnhub news with FinBERT sentiment per article
- [x] 6-tab analyst sidebar with per-tab status indicators
- [x] TradingView charts (individual + compare overlay, theme-aware)
- [x] Risk & sentiment side-by-side in compare view
- [x] Three rotating log files (finsight, llm, tasks)
- [x] Session persistence across browser refresh (localStorage)
- [x] Unit tests — backend (pytest) + frontend (vitest)
- [x] RAGAS eval baseline (10 hand-curated Q&A pairs)
- [x] Langfuse tracing — `@observe` across all LLM calls, RAG retrieval, ingest, report, debate. Nested span hierarchy with cost + latency per generation
- [x] MIT License

### In Progress / Next
- [ ] **Structured agent report protocol** — Pydantic typed outputs between agents (before CrewAI)
- [ ] **RAGAS eval run** — score current retrieval quality as baseline before agent changes

### Planned
- [ ] **CrewAI analyst crew** — 4 parallel analysts (Fundamentals, News, Sentiment, Risk) + Bull/Bear researchers + Report Writer
- [ ] **LangGraph orchestrator** — StateGraph with ReAct prompting, parallel analyst nodes, Bull/Bear debate rounds, Risk Manager gate
- [ ] **Portfolio signal agent** — BUY/HOLD/SELL + confidence score as final pipeline output
- [ ] **EDGAR MCP server** — FastMCP exposing fetch_10k, search_filings, get_xbrl as tools. Compatible with Claude Code, Ruflo, and any MCP client
- [ ] **LangGraph checkpoint resumption** — RedisSaver crash-safe pipeline (60–120s runs)
- [ ] **Full citation trail** — every finding traces to exact filing chunk
- [ ] **Persistent analysis journal** — risk score / sentiment tracked over time per company
- [ ] **Multi-filing RAG** — cross-year questions ("how have risks changed over 3 years?")
- [ ] **Competitor extraction** — spaCy NER on Item 1 → ticker-matched competitor graph
- [ ] **Peer auto-suggest** — SIC code matching for automatic peer group discovery
- [ ] **Segment revenue breakdown** — XBRL segment data, donut chart per company
- [ ] **Event timeline** — 8-K events overlaid on price chart
- [ ] **GCP Cloud Run deployment** — containerised, auto-scaling, target Day 70

---

## Design Decisions

**Why XBRL over LLM for financial numbers?** LLMs hallucinate figures. XBRL is the authoritative machine-readable data the company filed with the SEC. Deterministic always beats probabilistic for numbers.

**Why fastembed over sentence-transformers?** fastembed uses ONNX runtime — no PyTorch, no CUDA dependency. The Docker image stays lean and runs on any CPU. Same BGE model, fraction of the overhead.

**Why hybrid search (BM25 + dense)?** Financial documents contain exact terminology — "EBITDA", "goodwill impairment", "Section 382 limitation" — that semantic embeddings can miss or conflate. BM25 handles exact terms; dense handles meaning. RRF merges both.

**Why a cross-encoder reranker?** Cosine similarity measures vector proximity, not answer relevance. A chunk titled "Geographic Concentration Risk" won't match a query for "supply chain risks" semantically — but a cross-encoder reading both understands the connection. Two-stage retrieval (fast ANN → precise rerank) is the production standard.

**Why DeepSeek as primary LLM?** Comparable quality to GPT-4 for financial document analysis at ~800x lower cost. Every call logs cost — the savings story becomes a LangFuse interview talking point.

**Why Celery over async tasks?** `async/await` keeps the HTTP request open — a 30-60 second ingest would time out browsers. Celery returns a `task_id` immediately; the pipeline runs in a worker process. The request/response separation is the right pattern for long-running jobs.

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built by [Kural](https://github.com/XGboost2) · 100-day AI engineering upskill · Prague, 2026*
