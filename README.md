# FinSight AI

**Financial Risk Intelligence Platform** — ingests SEC EDGAR 10-K, 10-Q, and 8-K filings, supports user-uploaded business documents, stores filings across vector and graph retrieval layers, and delivers AI-powered fundamental analysis grounded in source documents.

Built as a portfolio project demonstrating production-grade AI engineering: LangGraph multi-agent pipeline with Pydantic AI typed contracts, dual RAG retrieval (Qdrant vector RAG + PageIndex-style vectorless retrieval), Neo4j graph RAG for uploaded documents, MarkItDown multi-format document conversion, cross-encoder reranking, Celery background ingestion, deterministic XBRL financial parsing, FinBERT sentiment analysis, DeepEval evaluation baseline, multi-provider LLM routing with cost tracking, and a fully reactive analyst UI.

---

## What It Does

Search any SEC-registered company → FinSight fetches its latest filings from EDGAR, embeds them into a hybrid vector store, and generates a comprehensive equity research report in the style of a professional analyst note — with risk scoring, sentiment analysis, YoY risk diff, technical indicators, and a bull/bear debate transcript.

Upload a custom document → FinSight converts it with Microsoft MarkItDown, chunks it, stores it in Neo4j as a `Document → Section → Chunk` graph, and lets the chat endpoint answer against that uploaded document through a vectorless graph RAG path.

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
| **MarkItDown Upload Conversion** | `POST /api/documents/ingest` accepts uploaded business documents, converts them to Markdown-like text with Microsoft MarkItDown, chunks the result, and registers the file as a chat-ready document |

### RAG Pipeline
| Feature | Detail |
|---------|--------|
| **BGE Embeddings** | `BAAI/bge-base-en-v1.5` via fastembed (ONNX, CPU-only, 768-dim). No PyTorch, no GPU. Matches OpenAI ada-002 quality at zero API cost |
| **Hybrid Search** | Dense (cosine) + sparse (BM25/IDF) vectors in Qdrant, fused with Reciprocal Rank Fusion (RRF). Exact financial jargon (BM25) + semantic meaning (dense) |
| **Cross-Encoder Reranker** | `BAAI/bge-reranker-base` (280MB ONNX, CPU) rescores top-20 RRF candidates for true relevance. Catches cases where similarity ≠ relevance — e.g. "supply chain risks" → "Geographic Concentration Risk" section |
| **Cross-Filing Retrieval** | RAG search across 10-K + 10-Q simultaneously via Qdrant `MatchAny` filter. Enables quarterly trend questions over annual filings |
| **Multi-Query Retrieval** | Chat endpoint issues both the original question and section-targeted rephrasing to improve recall on topic-specific queries |
| **Fusion Retrieval Mode** | Optional `RETRIEVAL_MODE=fusion` combines vector RAG with PageIndex-style vectorless section retrieval, dedupes candidates by filing/chunk, then reranks the final set |
| **LLM Section Reasoner** | Uses `CHEAP_MODEL` to infer likely filing sections for a question, caches decisions in Redis, and falls back to deterministic regex routing if the LLM helper fails |
| **Neo4j Graph RAG** | Uploaded documents are stored locally in Neo4j as `Document → Section → Chunk` and retrieved through lexical + section-aware vectorless scoring. Useful for explainable graph-backed RAG demos |

### AI Analysis
| Feature | Detail |
|---------|--------|
| **LangGraph Pipeline** | `StateGraph` fan-out/fan-in: 5 nodes run in parallel (fundamentals, risk, sentiment, news, technical) → bull → bear → report → portfolio. Typed Pydantic contracts at every boundary. `GET /api/companies/{ticker}/analysis`. 24h Redis cache |
| **Pydantic AI Agents** | `FundamentalsAnalyst` + `RiskAnalyst` (deepseek-chat, typed tool outputs). `BullResearcher` + `BearResearcher` (sequential debate, Bear has live `search_risk_evidence` RAG tool) + `ReportWriter`. `result_type` enforced — validated output or exception, no raw JSON parsing |
| **Comprehensive Analysis Report** | Full equity research note: findings table (Revenue / Profitability / Risk / Sentiment with signal badges), risk score gauge (0–100), trend narrative, management themes, bull/bear case bullets, verdict |
| **Portfolio Signal Agent** | Final `node_portfolio` LangGraph node after ReportWriter — reads all analyst + debate outputs and produces typed `PortfolioSignal` (BUY/HOLD/SELL, confidence, rationale, key_factors, risk_reward). Displayed as badge above Verdict |
| **Full Citation Trail** | `citations: list[RagChunk]` on `ReportOutput` — deduped by `chunk_index` from `fundamentals.chunks + risk.chunks`. Flows end-to-end: RAG → RagChunk → node_report → `AnalysisReport.citations` → API response |
| **FinBERT Sentiment** | `ProsusAI/finbert` runs locally on CPU — zero API cost. Scores MD&A (Item 7) chunks: positive / negative / neutral. Aggregates to continuous scalar `(avg_pos - avg_neg + 1) / 2`. Filters boilerplate before inference |
| **YoY Risk Factor Diff** | Compares Item 1A text between current and prior year 10-K using `difflib` + BGE semantic matching. Classifies paragraphs as new / changed / removed / unchanged. Handles rewording that isn't a real change |
| **Bull/Bear Debate** | Real sequential Pydantic AI agents. Bull reads all analyst outputs → typed `BullCase`. Bear reads BullCase + calls `search_risk_evidence` (live RAG) to retrieve counter-evidence → typed `BearCase`. ReportWriter synthesises both → `ReportOutput` |
| **Technical Analysis** | yfinance fetches 1-year daily OHLCV. Computes RSI(14), MACD(12,26,9), SMA50, SMA200, Bollinger Bands (20,2), Volume ratio. LLM generates verdict. TradingView Technical Analysis widget alongside |
| **Company News** | Finnhub API — recent headlines with FinBERT sentiment per article. 1hr Redis cache |

### LLM Infrastructure
| Feature | Detail |
|---------|--------|
| **Multi-Provider Routing** | Kimi/Moonshot AI (primary) → DeepSeek (secondary) → Anthropic Claude → OpenAI → mock response. App never crashes on missing keys |
| **Smart Model Router** | Auto-routes all queries to `kimi-k2.6` (256k context window handles both simple and complex). DeepSeek Flash is the fallback if Kimi is unavailable. Keywords like "analyse", "compare", "why" + queries >200 chars trigger the power path |
| **Per-Request Model Override** | 8-model pill selector in the chat panel. Choose DeepSeek Chat/Reasoner, Claude Haiku/Sonnet/Opus, or GPT-4o per query |
| **LLM Cost Tracker** | Atomic Redis cost recording per call with model, tokens_in, tokens_out, cost_usd, latency_ms. Aggregates day/week/month with per-model breakdown. `$` button in topbar |
| **JSON Repair** | `json-repair` library + 3-attempt retry for malformed LLM JSON output. Logs which attempt succeeded for prompt quality monitoring |

### Production Hardening
| Feature | Detail |
|---------|--------|
| **Rate Limiting** | `slowapi` backed by Redis (shared across Uvicorn workers). Per-endpoint limits: ingest 5/min, diff 5/min, sentiment 5/min, report 10/min, compare 10/min, technicals 20/min, news 20/min, dashboard 30/min, search 60/min. Returns 429 + Retry-After |
| **Structured Logging** | Three rotating log files: `finsight.log` (all), `llm.log` (LLM calls only), `tasks.log` (Celery). 10MB × 5 backups each. Named loggers with propagation |
| **Langfuse Tracing** | Full `@observe` instrumentation across every LLM call, RAG retrieval, ingest, report generation, and debate. Nested span hierarchy: `report-lookup → report-generate → retrieve-multi × 5 → call-llm-raw + debate`. Chat turns grouped into Langfuse sessions via `propagate_attributes(session_id=...)` — full conversation replay in dashboard. Cache hits visible. No-op when keys absent |
| **LLM-as-Judge** | `services/judge.py` — after every pipeline run, a second `CHEAP_MODEL` call scores the report on 4 dimensions (faithfulness, risk coverage, debate quality, recommendation clarity). All 5 scores pushed to Langfuse as trace-level numeric scores via `create_score()`. Never raises — zero scores on failure, pipeline unaffected |
| **Redis TTL Strategy** | Different TTLs per data type: sentiment 30d, diff 30d, report 24h, dashboard 7d, news 1hr, technicals 1hr. Matches how often data actually changes |
| **Session Persistence** | Last selected company persists across browser refresh via localStorage. Restore is two fast Redis reads — no pipeline re-execution |
| **Graceful Degradation** | Every LLM call has a mock fallback. Reranker falls back to RRF order on failure. News failures don't block the report |
| **LangGraph Checkpointing** | `MemorySaver` singleton in `graph.py` — stable `thread_id = "finsight:{ticker}:{filing_id}"` for in-process state inspection. `refresh=True` appends UUID suffix for clean re-runs. Note: in-memory only; state does not survive worker restarts |

### Frontend
| Feature | Detail |
|---------|--------|
| **6-Tab Analyst Sidebar** | Fundamentals · News · Sentiment · Risk · Technical · Bull vs Bear. Each tab shows pulsing loader while fetching, status indicator when done |
| **Comprehensive Report View** | Company overview, findings table with signal badges (✅ ⚠️ 🔴 ℹ️), financial trend narrative, risk gauge + sentiment badge side-by-side, top risk factors, management themes, colour-coded verdict |
| **Risk Tab** | Risk score gauge, top risk factor bullets, 8-K event feed, YoY diff (new/changed/removed paragraphs) |
| **Sentiment Tab** | FinBERT score with breakdown (positive/negative/neutral class probabilities), most polarised MD&A sentences |
| **Technical Tab** | Computed indicators table (RSI, MACD, SMA50/200, Bollinger Bands, Volume), AI verdict paragraph, signal breakdown (buy/neutral/sell counts), TradingView Technical Analysis widget |
| **Bull vs Bear Tab** | Bull case bullets, Bear case bullets, 4-turn LLM debate transcript, debate winner display (Bull/Bear/Draw) |
| **CitationPanel** | Collapsible panel below Verdict — treasury-green left-border cards, [N] citation index, section label (`item` field), "SEC 10-K" source tag, expand/collapse per chunk. Only shown in full (non-compact) report view |
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
      │     document_converter.py    ← MarkItDown conversion for uploaded PDFs, Office files, HTML, CSV, JSON, XML, text, etc.
      │     chunker.py               ← paragraph-aware chunking (1000 char / 200 overlap)
      │     xbrl.py                  ← XBRL financial facts (revenue, income, margin, YoY)
      │     sections.py              ← 10-K section extractor (Item 1, 1A, 7, 8)
      │     news.py                  ← Finnhub news + FinBERT sentiment per article
      │
      ├── rag/
      │     embedder.py              ← fastembed + BAAI/bge-base-en-v1.5 (ONNX, CPU, 768-dim)
      │     retriever.py             ← Qdrant hybrid search (dense + sparse, RRF fusion)
      │     pipeline.py              ← ingest / retrieve / retrieve_multi + fusion retrieval (with reranking)
      │     reranker.py              ← BAAI/bge-reranker-base cross-encoder (ONNX, CPU)
      │     graph_store.py           ← Neo4j uploaded-document graph RAG
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
      ├── agents/
      │     contracts.py             ← Pydantic I/O contracts (FundamentalsOutput, RiskOutput, TechnicalOutput, BullCase, BearCase, ReportOutput, PortfolioSignal; citations: list[RagChunk] on ReportOutput)
      │     state.py                 ← AnalysisState TypedDict with typed node outputs
      │     analyst_agents.py        ← FundamentalsAnalyst + RiskAnalyst (Pydantic AI, deepseek-chat, typed tool outputs)
      │     debate_agents.py         ← BullResearcher, BearResearcher (search_risk_evidence tool), ReportWriter (Pydantic AI)
      │     nodes.py                 ← node_fundamentals, node_risk, node_sentiment, node_news, node_technical, node_bull, node_bear, node_report, node_portfolio
      │     graph.py                 ← StateGraph: START → [5 parallel nodes] → bull → bear → report → portfolio → END. AsyncRedisSaver checkpointer (0.4.1)
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
  Qdrant :6333   Neo4j :7687    Redis DB0      Redis DB1     Flower :5555
  (vectors)      (graph RAG)    (app data)     (Celery)      (task monitor)
```

### RAG Retrieval Pipeline

```
User query
    ↓
Section intent detection — regex routes query to Item numbers
  e.g. "risk" → Item 1A only · "revenue" → Item 7 only
    ↓
BGE embed (query) + sparse encode
    ↓
Qdrant hybrid search — top candidates (section-filtered)
  ├── Dense branch: cosine similarity (BAAI/bge-base-en-v1.5)
  └── Sparse branch: BM25/IDF (exact financial term matching)
    ↓
Reciprocal Rank Fusion (RRF) — merges dense + sparse ranked lists
    ↓
BGE reranker (BAAI/bge-reranker-base) — reads query + chunk together, scores relevance
    ↓
Top 3 chunks (section-filtered) or top 5 (unfiltered) → LLM context
```

Section routing reduced hallucination by 30% (0.20 → 0.14) by eliminating irrelevant chunks before they reach the LLM.

### Fusion RAG Pipeline

```
User query
    ↓
LLM section reasoner + regex fallback
    ↓
Two candidate generators
  ├── Vector path: Qdrant dense+sparse retrieval
  └── Vectorless path: PageIndex-style section/chunk retrieval
    ↓
Deduplicate by (filing_id, chunk_index)
    ↓
Cross-encoder reranker
    ↓
Top evidence chunks → LLM context
```

This mode is controlled with `RETRIEVAL_MODE=fusion`. The default remains `hybrid` so the existing Qdrant path is stable, while the fusion path can be enabled for experiments and demos.

### Uploaded Document Graph RAG

```
Upload file
    ↓
MarkItDown conversion
    ↓
Paragraph-aware chunking
    ↓
Neo4j graph insert
  (:Document)-[:HAS_SECTION]->(:Section)-[:HAS_CHUNK]->(:Chunk)
    ↓
Chat request with filing_id
    ↓
Neo4j vectorless graph retrieval
    ↓
LLM grounded answer
```

Uploaded documents use Neo4j rather than Qdrant embeddings so the project can demonstrate graph-backed RAG with an inspectable local graph database.

### LLM Routing

| Query type | Model | Cost / 1M tokens |
|------------|-------|-----------------|
| All queries (primary) | `kimi-k2.6` | $0.15 in / $0.60 out |
| Fallback (Kimi unavailable) | `deepseek-v4-flash` | $0.14 in / $0.28 out |
| User override | Any of 8 models | varies |

**Fallback chain:** Kimi → DeepSeek → Anthropic Claude → OpenAI → mock response

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
| Graph DB | Neo4j 5 Community — uploaded-document graph RAG, `Document → Section → Chunk` model |
| Document Conversion | Microsoft MarkItDown — multi-format uploads converted into Markdown-like text for chunking |
| Sentiment | `ProsusAI/finbert` via HuggingFace transformers (CPU, 110M params) |
| Agent Orchestration | LangGraph 0.2+ — `StateGraph` fan-out/fan-in parallelism, typed state |
| Agent Contracts | Pydantic AI (next) — typed tool outputs, `result_type` enforcement |
| LLM | Kimi/Moonshot AI (primary, `kimi-k2.6`) · DeepSeek (secondary) · Anthropic Claude · OpenAI (switchable per-request) |
| Observability | Langfuse 3 — `@observe` tracing, nested spans, cost + latency per call |
| Eval | DeepEval — 6 RAG metrics, DeepSeek judge, 20 Q&A pairs, result caching |
| Financial Data | SEC EDGAR XBRL API (deterministic) · yfinance (technical indicators) |
| News | Finnhub API |
| Cache | Redis 8 — DB 0: app data · DB 1: Celery broker/backend |
| Background Tasks | Celery 5 + Flower (monitoring at :5555) |
| Scheduler | APScheduler 3.10 (daily 02:00 UTC ticker refresh) |
| JSON Reliability | json-repair + 3-attempt retry for malformed LLM output |
| Frontend | React 19 + Vite, TradingView Widgets, Lucide icons |
| Containers | Docker + Docker Compose (backend, frontend, worker, Redis, Qdrant, Neo4j, Flower) |

---

## API Endpoints

| Method | Path | Rate Limit | Description |
|--------|------|-----------|-------------|
| `POST` | `/api/companies/{ticker}/ingest` | 5/min | Queue Celery ingest task. Returns `task_id` |
| `GET` | `/api/companies/{ticker}/ingest/status` | — | Poll Celery task status + progress step |
| `GET` | `/api/companies/{ticker}/analysis` | 5/min | LangGraph pipeline report. `?refresh=true` to regenerate |
| `GET` | `/api/companies/{ticker}/report` | 10/min | Legacy sequential report (fallback) |
| `GET` | `/api/companies/{ticker}/dashboard` | 30/min | XBRL metrics + LLM narrative |
| `GET` | `/api/companies/{ticker}/diff` | 5/min | YoY risk factor diff (new/changed/removed) |
| `GET` | `/api/companies/{ticker}/sentiment` | 5/min | FinBERT MD&A sentiment score |
| `GET` | `/api/companies/{ticker}/technicals` | 20/min | RSI, MACD, SMA50/200, Bollinger Bands + LLM verdict |
| `GET` | `/api/companies/{ticker}/news` | 20/min | Finnhub headlines + FinBERT sentiment |
| `GET` | `/api/companies/{ticker}/events` | — | Recent 8-K events classified by type |
| `POST` | `/api/documents/ingest` | 3/min | Upload a custom document. MarkItDown conversion → chunking → Neo4j graph RAG registration |
| `POST` | `/api/companies/compare` | 10/min | Two-ticker head-to-head with YoY revenue trend |
| `POST` | `/api/chat` | — | RAG Q&A with optional model override and optional `filing_id` for uploaded documents |
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
| Neo4j browser | http://localhost:7474 |
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
docker compose up qdrant redis neo4j
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

# Infrastructure — values are passed to Docker at runtime from .env
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=

# Redis
REDIS_PASSWORD=replace_with_local_redis_password
REDIS_URL=redis://:replace_with_local_redis_password@redis:6379

# Neo4j graph RAG for uploaded documents
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=replace_with_local_neo4j_password
NEO4J_AUTH=neo4j/replace_with_local_neo4j_password
NEO4J_DATABASE=neo4j

# Retrieval mode
# hybrid = existing Qdrant dense+sparse RRF path
# fusion = Qdrant vector RAG + PageIndex-style vectorless retrieval + reranking
RETRIEVAL_MODE=hybrid
SECTION_REASONER_CACHE_TTL_SECONDS=604800

# Uploads
DOCUMENT_UPLOAD_MAX_BYTES=26214400

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
│   │   ├── document_converter.py      ← MarkItDown upload conversion
│   │   ├── chunker.py                 ← paragraph-aware splitter
│   │   ├── sections.py                ← 10-K section extractor (Item 1/1A/7/8)
│   │   ├── xbrl.py                    ← XBRL financials + YoY trend
│   │   └── news.py                    ← Finnhub news + FinBERT per article
│   ├── rag/
│   │   ├── embedder.py                ← fastembed BGE wrapper
│   │   ├── retriever.py               ← Qdrant hybrid search (dense + sparse, RRF)
│   │   ├── pipeline.py                ← ingest / retrieve / retrieve_multi + fusion retrieval + reranking
│   │   ├── graph_store.py             ← Neo4j uploaded-document graph RAG
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
│           ├── CitationPanel.jsx      ← collapsible citation cards (treasury-green, [N] index, SEC 10-K source tag)
│           ├── StatusDots.jsx         ← Redis/Qdrant health indicators
│           └── tabs/
│               ├── RiskTab.jsx        ← risk gauge, factors, 8-K events, YoY diff
│               ├── SentimentTab.jsx   ← FinBERT score, breakdown, sentences
│               ├── BullBearTab.jsx    ← bull/bear bullets + debate transcript + winner display
│               ├── TechnicalTab.jsx   ← computed indicators + LLM verdict + TV widget
│               └── NewsTab.jsx        ← Finnhub headlines + sentiment badges
└── tests/
    ├── conftest.py
    ├── test_routes.py
    ├── test_graph_store.py            ← Neo4j graph RAG unit tests with fake driver/session
    ├── test_rag_pipeline.py           ← fusion retrieval / section-reasoning tests
    └── eval_baseline/
        ├── run_eval.py                ← DeepEval runner — 6 metrics, custom DeepSeekJudge, caching
        ├── questions.json             ← 20 hand-curated Q&A pairs with ground truth across 5 tickers
        ├── baseline_scores.json       ← locked baseline scores (updated each --set-baseline run)
        └── results/                   ← timestamped per-run score history
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
- [x] Langfuse tracing — `@observe` across all LLM calls, RAG retrieval, ingest, report, debate. Nested span hierarchy with cost + latency per generation
- [x] **DeepEval baseline** — faithfulness 0.85 · answer relevancy 0.85 · hallucination 0.14 · contextual recall 0.83 · contextual precision 0.45 · contextual relevancy 0.33. Custom DeepSeekJudge wrapper (`max_tokens=8192`), 20 hand-curated Q&A pairs with ground truth across 5 tickers, result caching, weekly CI gate
- [x] **Section-aware retrieval** — query intent routing to 10-K sections (Item 1A for risk, Item 7 for financials, etc.) via Qdrant `item` filter. Reduces irrelevant chunk co-retrieval. Hallucination dropped from 0.20 → 0.14 (-30%)
- [x] MIT License

- [x] **LangGraph analysis pipeline** — `StateGraph` with fan-out/fan-in parallelism. 5 nodes run simultaneously (fundamentals/XBRL, risk/RAG, FinBERT sentiment, Finnhub news, technical indicators) → bull → bear → report. Exposed at `GET /api/companies/{ticker}/analysis`. 24h Redis cache
- [x] **Pydantic AI agents** — `FundamentalsAnalyst` + `RiskAnalyst` (typed tool outputs, deepseek-chat). `BullResearcher` + `BearResearcher` (sequential debate, Bear has live `search_risk_evidence` RAG tool) + `ReportWriter`. `result_type` enforced at every agent boundary
- [x] **Real Bull/Bear debate** — Bull reads all 5 analyst outputs → typed `BullCase`. Bear reads BullCase + retrieves Item 1A counter-evidence via RAG tool → typed `BearCase`. Replaces old single-LLM-call simulation
- [x] **TechnicalAnalyst node** — 5th parallel node. RSI, MACD, SMA50/200, Bollinger Bands, volume fed into `DebateDeps`. Bull prompt flags fundamental/technical convergence; Bear prompt surfaces RSI overbought and sell signals
- [x] **Portfolio signal agent** — BUY/HOLD/SELL + confidence score as final LangGraph node (`node_portfolio`). Typed `PortfolioSignal` contract wired into `AnalysisState` and `AnalysisReport.portfolio_signal`
- [x] **LangGraph checkpointing** — `MemorySaver` singleton, stable `thread_id = "finsight:{ticker}:{filing_id}"`, `refresh=True` for clean re-runs
- [x] **Full citation trail** — `citations: list[RagChunk]` deduped by `chunk_index`. Flows RAG → node_report → API response. `CitationPanel.jsx` collapsible below Verdict
- [x] **LLM-as-judge** — `services/judge.py` scores every pipeline run on 4 dimensions (faithfulness, risk coverage, debate quality, recommendation clarity) and pushes all 5 scores to Langfuse via `create_score()`. Uses `CHEAP_MODEL` (Kimi), never raises
- [x] **Langfuse session grouping** — chat turns linked to Langfuse sessions via `propagate_attributes(session_id=...)`. Full conversation replay visible in Langfuse dashboard
- [x] **Kimi/Moonshot AI primary LLM** — migrated from DeepSeek to `kimi-k2.6` as primary. 256k context, $0.15/$0.60 per 1M tokens. DeepSeek Flash retained as secondary fallback
- [x] **Dual RAG retrieval** — optional fusion mode combines Qdrant vector retrieval with PageIndex-style vectorless section retrieval, dedupes candidates, and reranks the merged evidence set
- [x] **MarkItDown document uploads** — upload endpoint converts many business file formats into Markdown-like text before chunking
- [x] **Neo4j graph RAG for uploads** — local graph database stores uploaded documents as `Document → Section → Chunk`; chat can target a specific uploaded `filing_id`

### Planned
- [ ] **EDGAR MCP server** — FastMCP exposing fetch_10k, search_filings, get_xbrl as tools. Compatible with Claude Code and any MCP client
- [ ] **Persistent analysis journal** — risk score / sentiment tracked over time per company
- [ ] **Multi-filing RAG** — cross-year questions ("how have risks changed over 3 years?")
- [ ] **Competitor extraction** — spaCy NER on Item 1 → ticker-matched competitor graph
- [ ] **Peer auto-suggest** — SIC code matching for automatic peer group discovery
- [ ] **Segment revenue breakdown** — XBRL segment data, donut chart per company
- [ ] **GCP Cloud Run deployment** — containerised, auto-scaling, target Day 70

---

## Design Decisions

**Why XBRL over LLM for financial numbers?** LLMs hallucinate figures. XBRL is the authoritative machine-readable data the company filed with the SEC. Deterministic always beats probabilistic for numbers.

**Why fastembed over sentence-transformers?** fastembed uses ONNX runtime — no PyTorch, no CUDA dependency. The Docker image stays lean and runs on any CPU. Same BGE model, fraction of the overhead.

**Why hybrid search (BM25 + dense)?** Financial documents contain exact terminology — "EBITDA", "goodwill impairment", "Section 382 limitation" — that semantic embeddings can miss or conflate. BM25 handles exact terms; dense handles meaning. RRF merges both.

**Why a cross-encoder reranker?** Cosine similarity measures vector proximity, not answer relevance. A chunk titled "Geographic Concentration Risk" won't match a query for "supply chain risks" semantically — but a cross-encoder reading both understands the connection. Two-stage retrieval (fast ANN → precise rerank) is the production standard.

**Why Kimi as primary LLM?** `kimi-k2.6` has a 256k context window, handles both simple and complex financial queries in a single model, and costs $0.15/$0.60 per 1M tokens — comparable to DeepSeek Flash but with far more context headroom for multi-filing analysis. Every call logs cost — the savings story becomes a Langfuse interview talking point.

**Why Celery over async tasks?** `async/await` keeps the HTTP request open — a 30-60 second ingest would time out browsers. Celery returns a `task_id` immediately; the pipeline runs in a worker process. The request/response separation is the right pattern for long-running jobs.

**Why Pydantic AI over CrewAI?** Pydantic AI agents return typed Pydantic models directly (`result_type=RiskOutput`) — enforced at the boundary, not parsed from strings. No second orchestration layer competing with LangGraph. Consistent with the rest of the codebase. CrewAI's role/backstory prompting is cosmetic; Pydantic AI's typed contracts are structural.

**Why LangGraph as orchestrator?** The analysis pipeline is a DAG with parallel branches and a fan-in synthesis step — exactly what `StateGraph` is built for. LangGraph provides checkpointing, typed state, and explicit node/edge definitions. Plain `asyncio.gather` would work but gives no observability, resumption, or state inspection.

**Why dual RAG instead of only vector search?** Embeddings are strong for semantic similarity, but SEC filings have predictable structure. Risk questions often map to Item 1A, revenue questions to MD&A, and recent event questions to 8-K content. The fusion path combines vector recall with PageIndex-style section retrieval, then reranks the merged evidence so the LLM receives fewer irrelevant chunks.

**Why MarkItDown for uploads?** Real business users upload PDFs, Office files, spreadsheets, HTML, CSV, JSON, XML, and plain text. MarkItDown provides a common conversion layer into Markdown-like text, which keeps ingestion maintainable instead of writing one parser per file type.

**Why Neo4j for uploaded-document RAG?** Uploaded files naturally have document structure: documents contain sections, sections contain chunks, and future versions can connect chunks to companies, risks, dates, events, and metrics. Neo4j makes those relationships explicit and inspectable. Qdrant remains the better fit for high-volume vector similarity search, so the system uses both databases for different retrieval jobs.

---

## Changelog

### Day 60 — 2026-06-17

**Dual RAG and Graph RAG**
- Added `RETRIEVAL_MODE=hybrid|fusion`. `fusion` combines Qdrant vector retrieval with PageIndex-style vectorless section retrieval, dedupes by `(filing_id, chunk_index)`, and reranks the final candidate set
- Added LLM section reasoner using `CHEAP_MODEL`, Redis cache key `llm_cache:sections:*`, 7-day TTL, and regex fallback
- Added `backend/rag/graph_store.py` with Neo4j local graph RAG for uploaded documents
- Graph model: `(:Document)-[:HAS_SECTION]->(:Section)-[:HAS_CHUNK]->(:Chunk)`
- Added Neo4j schema setup for unique `Document.filing_id` plus section/chunk indexes

**Document Uploads**
- Added `backend/ingestion/document_converter.py` using Microsoft MarkItDown
- Added `POST /api/documents/ingest` with multipart upload, ticker, filing type, company name, and filed date metadata
- Upload path converts file → chunks text → stores filing metadata → inserts graph nodes into Neo4j → registers the filing for chat
- Added optional `filing_id` to `/api/chat` so uploaded documents can be queried directly

**Infrastructure and Tests**
- Added Neo4j 5 Community service to Docker Compose with local browser on `127.0.0.1:7474` and Bolt on `127.0.0.1:7687`
- Added `neo4j>=5.25.0`, `python-multipart`, and `markitdown[all]` dependencies
- Added unit tests for fusion retrieval, upload ingestion, and Neo4j graph store behavior

### Day 25 — 2026-06-08

**Kimi primary LLM migration**
- `CHEAP_MODEL` and `POWER_MODEL` both set to `kimi-k2.6` (256k context). `CHEAP_FALLBACK = deepseek-v4-flash`
- Fallback chain: Kimi → DeepSeek → Anthropic Claude → OpenAI → mock
- `OpenAIModel` → `OpenAIChatModel` in Pydantic AI agent providers (API rename in pydantic-ai)
- Removed `langgraph-checkpoint-redis` dependency (incompatible with langgraph 0.2+); replaced with `MemorySaver`

**LLM-as-judge**
- `services/judge.py` — scores report on faithfulness, risk_coverage, debate_quality, recommendation_clarity (0.0–1.0 each)
- Pushes 5 numeric scores to Langfuse per pipeline run via `create_score()`; `judge.overall` score includes rationale comment
- `node_judge` wired as final LangGraph node after `node_portfolio`

**Langfuse SDK v3 migration**
- `langfuse_context.update_current_observation()` → `_lf().update_current_span()` / `update_current_generation()`
- `client.score()` → `client.create_score()` across `judge.py`, `routes.py`
- `usage={"unit": "TOKENS"}` → `usage_details={}` in generation updates

**Langfuse session grouping**
- Chat traces now attached to Langfuse sessions via `propagate_attributes(session_id=sid)` wrapping `ask_llm`
- Session replay visible in Langfuse dashboard — full conversation thread in one view

**Multi-filing chat RAG**
- Chat endpoint retrieves across 10-K + all ingested 10-Q filings simultaneously via `retrieve_multi`
- Recent 8-K events injected as text block from Redis (`finsight:events:8-K:{ticker}`) — last 10 events
- Added `quarter` / `recent` section query hints for quarterly earnings questions

### Day 17 — 2026-05-15

**Portfolio Signal Agent**
- New `node_portfolio` LangGraph node after ReportWriter — reads all analyst + debate outputs and produces typed `PortfolioSignal` (BUY/HOLD/SELL, confidence, rationale, key_factors, risk_reward)
- `PortfolioSignal` Pydantic contract in `agents/contracts.py`, wired into `AnalysisState` and serialised into `AnalysisReport.portfolio_signal`
- Debate winner display (Bull/Bear/Draw) added to BullBearTab

**Full Citation Trail**
- `citations: list[RagChunk]` on `ReportOutput` — deduped by `chunk_index` from `fundamentals.chunks + risk.chunks` in both the Pydantic AI agent path and the LLM fallback path
- `citations: list[dict]` on `AnalysisReport` — flows end-to-end: RAG → RagChunk → node_report → model_dump() → API response
- `CitationPanel.jsx` — collapsible panel below Verdict, treasury-green left-border cards, section label, [N] citation index, "SEC 10-K" source tag, expand/collapse per chunk

**LangGraph Checkpointing**
- `MemorySaver` singleton in `graph.py` — replaces `AsyncRedisSaver` (removed; incompatible with langgraph-checkpoint 4.x serializer)
- Stable `thread_id = "finsight:{ticker}:{filing_id}"` for in-process state inspection; `refresh=True` appends UUID suffix for clean re-runs
- `routes.py` passes `refresh` flag down to `run_analysis()`

### Day 16 — 2026-05-14

**Pydantic AI agent pipeline**
- Replaced all raw LangGraph node functions with typed Pydantic AI agents
- `FundamentalsAnalyst` + `RiskAnalyst` — synthesis-only agents (pre-retrieve context, single LLM call, no tool loops)
- `BullResearcher` + `BearResearcher` + `ReportWriter` — sequential debate chain, all synthesis-only with `retries=3`
- `TechnicalAnalyst` — 5th parallel analyst node; RSI, MACD, SMA50/200, Bollinger Bands, volume ratio fed into Bull/Bear prompts for fundamental/technical convergence detection

**Agent evaluation baseline**
- `tests/eval_baseline/run_agent_eval.py` — 4-metric DeepEval pipeline for agent output quality
- Custom `GEval` Agent Specificity metric: specificity **0.52 → 0.85** (measures whether bull/bear points cite exact numbers vs generic statements)
- Hallucination: 0.39 → 0.35 with typed contracts enforcing structured output
- Baseline locked: faithfulness 0.88 · answer relevancy 0.89 · hallucination 0.35 · specificity 0.85

**Security hardening** (code review)
- Ticker format validation (`^[A-Z0-9.\-]{1,10}$`) on every endpoint
- Admin endpoints (`/admin/costs`, `/admin/refresh-tickers`) require `X-Admin-Key` header
- CORS restricted from `allow_origins=["*"]` to configurable `CORS_ORIGINS` env var
- Redis password authentication; Qdrant + Redis ports bound to `127.0.0.1` only
- Error messages sanitized — internal exception details no longer exposed in 502 responses
- Frontend `sanitizeTicker()` prevents XSS via TradingView script injection
- `localStorage` validation prevents JSON injection on session restore

**Infrastructure**
- `@lru_cache` on Qdrant `_client()` — connection reused across requests
- Shared `httpx.AsyncClient` singleton in `llm.py` — no new client per LLM call
- `asyncio.Lock()` for thread-safe LangGraph graph compilation
- RSI division-by-zero bug fixed in `technical.py`
- `datetime.utcnow()` (deprecated) → `datetime.now(timezone.utc)`
- Docker healthchecks added for Redis and Qdrant
- Zustand state management + UI/theme redesign

**Tests**
- Rewrote full test suite to match Celery-based ingest API: 25/25 passing
- Added ticker format validation tests, admin auth tests, task_id format tests

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built by [Kural](https://github.com/XGboost2) · 100-day AI engineering upskill · Prague, 2026*
