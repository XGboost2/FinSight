# FEATURES.md — FinSight AI Feature Backlog

> This file is the single source of truth for what's built, what's next, and how to implement it.
> Read this before starting any new feature work.

---

## Status Legend
- ✅ Built
- 🔨 In progress
- 📋 Planned
- 💡 Idea / future

---

## What's Already Built

| Feature | Module | Notes |
|---------|--------|-------|
| ✅ SEC EDGAR 10-K ingestion | `ingestion/edgar.py` | Fetches latest 10-K via EDGAR REST API |
| ✅ Paragraph-aware chunker | `ingestion/chunker.py` | 1000 char chunks, 200 overlap |
| ✅ Vector embeddings | `rag/embedder.py` | fastembed + `BAAI/bge-base-en-v1.5` ONNX, 768-dim |
| ✅ Qdrant vector store | `rag/retriever.py` | Dense cosine similarity, `query_points` API |
| ✅ RAG Q&A pipeline | `rag/pipeline.py` | ingest + retrieve orchestration |
| ✅ LLM routing | `services/llm.py` | Claude primary, OpenAI fallback, mock dev mode |
| ✅ Dashboard metrics extraction | `services/dashboard.py` | LLM-extracted revenue, margins, risks, outlook |
| ✅ Company comparison | `services/comparison.py` | Two-ticker LLM head-to-head analysis |
| ✅ Redis ticker cache | `cache/ticker_cache.py` | ~13k SEC-registered companies, O(1) lookup |
| ✅ Filing registry | `cache/filing_registry.py` | Ingestion gate, Redis hash |
| ✅ REST API | `api/routes.py` | Ingest, chat, search, dashboard, compare, health |
| ✅ React frontend | `frontend/src/` | Search, dashboard, compare, filing chat panel |
| ✅ TradingView charts | `Dashboard.jsx`, `CompareView.jsx` | Live price charts |
| ✅ Redis + Qdrant status dots | `StatusDots.jsx` | Polls `/api/health` every 30s |
| ✅ Rotating file logger | `logging_config.py` | `backend/logs/finsight.log`, 10MB × 5 |
| ✅ Unit tests (backend) | `tests/test_routes.py` | pytest, all endpoints mocked |
| ✅ Unit tests (frontend) | `src/components/__tests__/` | vitest + RTL, all components |

---

## Feature Backlog — Priority Order

---

### 1. XBRL Parsing — replace LLM-based metric extraction
**Priority: HIGH — build next**

Currently `services/dashboard.py` uses an LLM to extract revenue, margins, etc. from raw text. This is slow, expensive, and unreliable across different company formats.

XBRL (eXtensible Business Reporting Language) gives deterministic, structured financial data directly from SEC EDGAR for all 10-Ks post-2009.

**What to build:**
- `ingestion/xbrl.py` — fetch XBRL filing data from `https://data.sec.gov/api/xbrl/companyfacts/{CIK}.json`
- Extract: `us-gaap/Revenues`, `us-gaap/NetIncomeLoss`, `us-gaap/GrossProfit`, `us-gaap/OperatingIncomeLoss`, `us-gaap/EarningsPerShareBasic`, `us-gaap/CommonStockSharesOutstanding`
- Return structured `FinancialFacts` Pydantic model with multiple years of data
- Replace LLM extraction in `dashboard.py` with XBRL facts where available, fall back to LLM for narrative fields

**API endpoint:**
```
GET /api/companies/{ticker}/financials   → multi-year GAAP facts
```

**Key EDGAR endpoint:**
```
https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
```

**Benefit:** Accurate numbers, no LLM cost, enables multi-year trend charts.

---

### 2. YoY Risk Factor Diff — highlight what changed year-over-year
**Priority: HIGH — strong differentiator**

Compare Item 1A (Risk Factors) text between the current 10-K and the prior year. New paragraphs = new threats. Removed paragraphs = resolved risks. Changed paragraphs = evolving concerns.

**What to build:**
- `ingestion/edgar.py` — extend to fetch prior year 10-K (already have filing list logic)
- `services/diff.py` — paragraph-level diff using `difflib.SequenceMatcher` or sentence embeddings for semantic similarity
- Classify each paragraph: `new` | `removed` | `changed` | `unchanged`
- New `DiffResponse` Pydantic model

**API endpoint:**
```
GET /api/companies/{ticker}/risk-diff?years=2    → paragraph-level diff
```

**Frontend:** New `RiskDiff.jsx` component — shows added paragraphs in green, removed in red, changed highlighted inline.

**Implementation note:** Use sentence embeddings (already have BGE) to match semantically similar paragraphs before falling back to string diff. This handles minor rewording that isn't a real change.

---

### 3. FinBERT Sentiment per Section — tone analysis across time
**Priority: HIGH — strong ML portfolio story**

Apply FinBERT to score the sentiment (positive / negative / neutral) of the MD&A section. Track this trend across filings to show if management language is becoming more cautious.

**What to build:**
- `services/sentiment.py` — load `ProsusAI/finbert` via `transformers` pipeline
- Run on chunked MD&A text (Item 7), aggregate scores per section
- Cache result in Redis (`sentiment:{filing_id}:{section}`, 30d TTL)
- Return per-section scores + overall sentiment trend if multiple years available

**Model:** `ProsusAI/finbert` — 110M BERT model, CPU-viable, finance-domain fine-tuned.

**API endpoint:**
```
GET /api/companies/{ticker}/sentiment    → section scores + trend
```

**Frontend:** Sentiment badge on dashboard (🟢 Positive / 🟡 Neutral / 🔴 Negative), trend sparkline if multi-year.

**Implementation note:** Don't run FinBERT on the full 100-page filing. Extract Item 7 chunks only (~10-20 chunks). Batch inference. Total latency <5s on CPU.

**Requirements to add:**
```
transformers>=4.40.0
torch>=2.0.0  # cpu only, pin to cpu build
```

---

### 4. Multi-Filing RAG — query across multiple years
**Priority: HIGH — where LangGraph earns its place**

Currently RAG is scoped to one filing per query. Multi-filing RAG lets users ask questions like:
- "How have Apple's risk factors changed over the last 3 years?"
- "Show revenue trend from 2021 to 2023"
- "When did management first mention AI as a risk?"

**What to build:**
- `ingestion/edgar.py` — fetch N most recent 10-Ks for a ticker (EDGAR filings endpoint already lists them)
- `rag/retriever.py` — add `search_multi` that queries across multiple `filing_id`s with a filter
- `services/multi_rag.py` — LangGraph workflow:
  1. `plan` — parse the question, determine how many filings needed
  2. `retrieve` — parallel retrieval across filing_ids
  3. `synthesize` — cross-filing answer with citations per filing
- New `MultiChatRequest` Pydantic model with optional `years` param

**API endpoint:**
```
POST /api/companies/{ticker}/multi-chat    → cross-filing RAG answer
```

**This is the natural forcing function for LangGraph** — parallel retrieval branches, conditional logic based on query intent.

**Qdrant note:** Each filing chunk already has `filing_id` in payload. Multi-filing search just passes multiple IDs to the `must` filter using `MatchAny`.

---

### 5. Segment Benchmarking — compare business segments across companies
**Priority: MEDIUM**

Many companies report revenue by segment (Apple: iPhone / Services / Mac / iPad / Wearables). XBRL exposes this via `us-gaap/SegmentReportingInformationRevenue`. Compare segment growth rates across competitors.

**What to build:**
- Extend XBRL parser (Feature 1) to extract segment data
- `services/segments.py` — normalise segment names across companies (use LLM for fuzzy matching)
- Add segment breakdown to `CompareResponse`

**API endpoint:**
```
GET /api/companies/{ticker}/segments     → segment revenue by year
POST /api/companies/compare-segments     → cross-company segment comparison
```

**Frontend:** Stacked bar chart in compare view showing segment splits side by side.

**Note:** Segment labels vary by company — "Services" at Apple is not the same as "Commercial Cloud" at Microsoft. LLM-assisted label normalisation needed.

---

### 6. Competitor Extraction — build a competitor graph from Item 1
**Priority: MEDIUM — good visual, quick win**

Companies are required to disclose their competitive landscape in Item 1. Extract competitor names using NER, build a graph of who considers whom a rival.

**What to build:**
- `services/competitors.py` — extract company names from Item 1 text using spaCy `en_core_web_sm` (ORG entities) or a targeted LLM prompt
- Match extracted names to SEC tickers via Redis ticker cache
- Store competitor graph in Redis (`competitors:{filing_id}`)

**API endpoint:**
```
GET /api/companies/{ticker}/competitors    → list of mentioned competitors with tickers
```

**Frontend:** `CompetitorGraph.jsx` — force-directed graph using D3.js or a lightweight library. Click a competitor node to load their dashboard.

**Requirements to add:**
```
spacy>=3.7.0
```

---

## Infrastructure Backlog

| Feature | Priority | Notes |
|---------|----------|-------|
| 📋 Hybrid BM25 + dense search | HIGH | Add sparse vectors to Qdrant, improves exact-term retrieval for financial jargon |
| 📋 LangFuse tracing | HIGH | Wire every LLM call through LangFuse — cost + latency dashboard |
| 📋 RAGAS eval baseline | HIGH | 10 Q&A pairs in `tests/eval_baseline/questions.json`, run weekly |
| 📋 PII filtering (presidio) | MEDIUM | GDPR — filter outputs before returning to frontend |
| 📋 GCP Cloud Run deployment | MEDIUM | Target Day 70 — containerise, push to Artifact Registry, deploy |
| 📋 LangGraph workflow | MEDIUM | Add when multi-filing RAG is built (Feature 4 above) |
| 💡 GraphQL endpoint | LOW | strawberry-graphql for flexible frontend queries |
| 💡 Celery async tasks | LOW | Move ingest to background task queue |
| 💡 FinE5 embeddings | LOW | `FinanceMTEB/FinE5` — 7B model, needs GPU — upgrade path only |

---

## Implementation Order (recommended)

```
Week 3-4:   XBRL parsing → replaces LLM metric extraction, saves cost
Week 4-5:   YoY Risk Diff → biggest visible feature, unique differentiator
Week 5-6:   FinBERT sentiment → ML story, quick to add on top of existing chunks
Week 6-7:   Multi-filing ingest + Multi-filing RAG + LangGraph
Week 7-8:   Segment benchmarking → builds on XBRL parser
Week 8:     Competitor extraction → NER, quick win
Week 8-9:   LangFuse + RAGAS → observability before deployment
Week 10:    GCP Cloud Run deployment
```

---

## Key Technical Decisions (locked)

- **Embeddings:** `fastembed` + `BAAI/bge-base-en-v1.5` (ONNX, CPU, 768-dim) — no torch in Docker
- **Vector DB:** Qdrant local (Docker) → Qdrant Cloud (1GB free) for production
- **LLM:** Anthropic Claude primary (`claude-haiku-4-5` cheap, `claude-opus-4-6` power) — OpenAI fallback
- **Cache:** Redis — all LLM responses cached SHA256 key, 30d TTL
- **No LangGraph yet** — add only when multi-filing RAG forces it (Feature 4)
- **No CrewAI yet** — add for report generation workflow post-Day 56
- **FinBERT runs CPU** — 110M model, batch inference on extracted section only
- **XBRL over LLM extraction** — deterministic numbers always preferred over LLM guessing

---

## Embedding Upgrade Path (future, not now)

| Model | Size | GPU needed | When |
|-------|------|-----------|------|
| `BAAI/bge-base-en-v1.5` (current) | 90MB ONNX | No | Now |
| `BAAI/bge-large-en-v1.5` | 300MB ONNX | No | When quality needs improvement |
| `FinanceMTEB/FinE5` | ~14GB | Yes | GCP deployment with GPU |
