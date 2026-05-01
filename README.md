# FinSight AI

Financial Risk Intelligence Platform that ingests SEC EDGAR 10-K filings, stores them as vector embeddings, and answers natural language questions grounded in the source documents. Built as a portfolio project demonstrating production-grade RAG on financial data.

---

## What It Does

- **Ingest a ticker** — fetches the latest 10-K from SEC EDGAR, parses and chunks it, embeds each chunk with BGE, stores vectors in Qdrant. Idempotent: re-ingesting the same ticker is a no-op.
- **Ask questions** — retrieves the top-5 semantically relevant chunks for a question, passes them as context to Claude (or GPT-4o as fallback), returns a grounded answer with citations and cost metadata.
- **Dashboard analytics** — LLM-extracted structured metrics per filing: revenue, net income, gross margin, top risk factors, revenue segments, management outlook.
- **Side-by-side comparison** — ingest two tickers, get an LLM analysis of their financials, risk profiles and business models head-to-head.
- **Company search** — autocomplete search across all SEC-registered companies backed by a Redis ticker index (~10k+ companies), zero API calls at query time.

---

## Architecture

```
React (Vite) :3000
      │
      ▼
FastAPI :8000  ──  APScheduler (daily ticker refresh)
      │
      ├── ingestion/
      │     edgar.py       ← SEC EDGAR API → 10-K HTML/text
      │     chunker.py     ← paragraph-aware chunking with overlap
      │
      ├── rag/
      │     embedder.py    ← fastembed + BAAI/bge-base-en-v1.5 (ONNX, CPU)
      │     retriever.py   ← Qdrant upsert + query_points
      │     pipeline.py    ← ingest() and retrieve() orchestration
      │
      ├── services/
      │     llm.py         ← Anthropic Claude primary, OpenAI fallback, mock dev mode
      │     dashboard.py   ← structured metric extraction per filing
      │     comparison.py  ← two-ticker LLM analysis
      │     store.py       ← in-memory BM25 fallback store
      │
      ├── cache/
      │     ticker_cache.py    ← SEC EDGAR ticker → CIK lookup, cached in Redis
      │     filing_registry.py ← Redis hash tracking ingested tickers
      │     redis_client.py    ← Redis singleton
      │
      └── api/routes.py   ← all REST endpoints, Pydantic I/O
      │
      ▼               ▼
   Qdrant :6333     Redis :6379
```

**LLM routing:**
- `claude-haiku-4-5` — simple single-doc Q&A (cheap, fast)
- `claude-opus-4-6` — multi-doc analysis, comparison (power)
- OpenAI `gpt-4o-mini` / `gpt-4o` — automatic fallback if no Anthropic key

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI 0.110+, Pydantic v2, uvicorn |
| Embeddings | fastembed 0.3.6 + `BAAI/bge-base-en-v1.5` (ONNX, no torch) |
| Vector DB | Qdrant 1.9+ (cosine similarity, 768-dim) |
| LLM | Anthropic Claude (primary) · OpenAI (fallback) |
| Cache | Redis 8 (ticker index, filing registry) |
| Scheduler | APScheduler 3.10 (daily 02:00 UTC ticker refresh) |
| Ingestion | SEC EDGAR REST API via httpx |
| Frontend | React 18 + Vite, component-based |
| Containers | Docker + Docker Compose |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ingest` | Fetch + embed a ticker's 10-K filing |
| `POST` | `/chat` | RAG query against an ingested filing |
| `GET` | `/search?q=apple` | Company search from Redis ticker cache |
| `GET` | `/dashboard/{ticker}` | Structured metrics extracted from filing |
| `POST` | `/compare` | Side-by-side LLM comparison of two tickers |
| `GET` | `/health` | Redis status + ingested filing count |
| `GET` | `/docs` | Auto-generated Swagger UI |

### Example: Ingest + Query

```bash
# Ingest Apple's latest 10-K
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL"}'

# Ask a question
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "question": "What are the main risk factors?"}'

# Compare two companies
curl -X POST http://localhost:8000/compare \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL", "MSFT"]}'
```

---

## Quickstart

### Docker (recommended)

```bash
# Copy and fill in API keys
cp .env.example .env

docker compose up --build
```

Services:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- Qdrant dashboard: http://localhost:6333/dashboard

### Local (no Docker)

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install && npm run dev

# Infrastructure (still needs Docker)
docker compose up qdrant redis
```

---

## Environment Variables

Create a `.env` file at the project root:

```env
# LLM — at least one required (falls back to mock mode if both missing)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Infrastructure — defaults work with docker-compose
QDRANT_URL=http://qdrant:6333
REDIS_URL=redis://redis:6379

# Optional
ALPHA_VANTAGE_KEY=        # reserved for market data (not yet used)
LANGFUSE_SECRET_KEY=      # reserved for tracing (not yet used)
LANGFUSE_PUBLIC_KEY=
```

---

## Frontend Components

| Component | Purpose |
|-----------|---------|
| `CompanySearch` | Autocomplete search backed by Redis ticker index |
| `FilingPanel` | Displays ingested filing metadata and triggers ingest |
| `Dashboard` | Renders LLM-extracted financial metrics |
| `CompareView` | Side-by-side ticker comparison UI |
| `StockChart` | Price chart (Alpha Vantage, in progress) |

---

## Repo Structure

```
finsight-ai/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── main.py              ← FastAPI app entry point
│   ├── config.py            ← Pydantic Settings, env vars
│   ├── requirements.txt
│   ├── api/routes.py        ← all endpoints
│   ├── models/schemas.py    ← Pydantic request/response models
│   ├── ingestion/
│   │   ├── edgar.py         ← SEC EDGAR fetch
│   │   └── chunker.py       ← paragraph-aware text splitter
│   ├── rag/
│   │   ├── embedder.py      ← fastembed wrapper
│   │   ├── retriever.py     ← Qdrant client
│   │   └── pipeline.py      ← ingest + retrieve orchestration
│   ├── services/
│   │   ├── llm.py           ← Claude + OpenAI + mock
│   │   ├── dashboard.py     ← metric extraction
│   │   ├── comparison.py    ← two-ticker analysis
│   │   └── store.py         ← in-memory BM25 fallback
│   ├── cache/
│   │   ├── redis_client.py
│   │   ├── ticker_cache.py
│   │   └── filing_registry.py
│   └── jobs/
│       └── refresh_tickers.py
└── frontend/
    ├── Dockerfile
    └── src/
        ├── App.jsx
        └── components/
            ├── CompanySearch.jsx
            ├── FilingPanel.jsx
            ├── Dashboard.jsx
            ├── CompareView.jsx
            └── StockChart.jsx
```

---

## Roadmap

- [ ] Hybrid BM25 + dense vector search (Qdrant sparse vectors)
- [ ] LangFuse tracing — cost and latency per request
- [ ] RAGAS evaluation baseline (10 hand-curated Q&A pairs)
- [ ] Multi-filing trend analysis (LangGraph orchestration)
- [ ] PII filtering via presidio-analyzer (GDPR, EU deployment)
- [ ] GCP Cloud Run deployment
- [ ] Upgrade embeddings to `FinanceMTEB/FinE5` (7B, GPU target)