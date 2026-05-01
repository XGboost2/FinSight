# FinSight Day 15: Final Master Plan
**Dashboard + Redis Caching + Smart Filing Pipeline + Comparison Engine**

---

## 1. When is the SEC API Called?
**Exactly twice per company. Ever.**

| Call | When | Why |
|------|------|-----|
| `GET company_tickers.json` | App startup (if Redis empty) | Load all 13k companies into Redis |
| `GET company_tickers.json` | Daily at 2am UTC | Refresh — add any newly listed companies |
| `GET EDGAR filing document` | User selects a new company | Fetch the actual 10-K text |

Everything else — dropdown search, CIK lookup, ticker resolution, filing registry, dashboard metrics, and comparison text — reads from Redis.

---

## 2. Architecture Flow

### Single Company Flow
```text
App startup
    ↓
Redis empty? → ONE call to SEC EDGAR → load 13,000 companies into Redis
    ↓ (never again until daily refresh)

User types "Apple"
    ↓
Backend: HGETALL finsight:tickers → filter in Python → return matches
    ↓ NO API CALL — pure Redis read

User selects "Apple Inc (AAPL)"
    ↓ POST /api/companies/AAPL/ingest
Backend checks Redis filing registry (finsight:filings)
    ├── AAPL already there? → return cached filing_id immediately (skip everything)
    └── Not there?
            ↓
        Fetch 10-K from SEC EDGAR  ← only API call from this point
            ↓
        Chunk (section-aware XBRL) → Embed → Qdrant
            ↓
        Extract dashboard metrics & Executive Summary via LLM
            ↓
        Write to Redis: finsight:dashboard:AAPL and finsight:filings
    ↓
GET /api/companies/AAPL/dashboard → read from Redis → render
```

---

## 3. Redis Key Design

```python
# ── Ticker index ──────────────────────────────────────────────────────
# Loaded once at startup from SEC EDGAR. Dropdown data source.
KEY:   finsight:tickers
TYPE:  Hash
VALUE: field = ticker (e.g. "AAPL")
       value = JSON { "name": "Apple Inc", "ticker": "AAPL", "cik": "0000320193" }

# ── Filing registry ───────────────────────────────────────────────────
# Tracks which tickers have been embedded. Gate for the embedding pipeline.
KEY:   finsight:filings
TYPE:  Hash
VALUE: field = ticker (e.g. "AAPL")
       value = JSON { "filing_id": "abc123", "filed_date": "2024-11-01", ... }

# ── Dashboard metrics cache ───────────────────────────────────────────
KEY:   finsight:dashboard:{ticker}
TYPE:  String (JSON)
TTL:   7 days

# ── Multi-Company Comparison cache ────────────────────────────────────
KEY:   finsight:compare:{ticker1}_{ticker2} (alphabetically sorted)
TYPE:  String (JSON)
TTL:   7 days
```

---

## 4. Main Page Dashboard (UI & Features)

**Goal:** Provide an immediate, context-rich dashboard integrating market sentiment (TradingView) and fundamental 10-K analysis.

### Dashboard UI Layout
```text
┌──────────────────────────────────────────────────────────────────────┐
│  Apple Inc (AAPL)   CIK: 0000320193  10-K FY24                       │
├──────────────────────────────────────────────────────────────────────┤
│  [ TradingView Advanced Chart Widget ]                               │
│  (Real-time price action & technicals embedded via frontend)         │
├──────────────────────────────────────────────────────────────────────┤
│  Executive Summary (10-K Context)                                    │
│  Apple's FY24 performance showed resilient growth driven by a 9%     │
│  increase in Services revenue...                                     │
├──────────┬──────────┬──────────┬─────────────────────────────────────┤
│ Revenue  │Net Income│  Margin  │   YoY Change                        │
│  $383B   │  $96.9B  │  45.2%   │    +2.9%                            │
├──────────┴──────────┴──────────┴─────────────────────────────────────┤
│ Revenue Segments                  Top Risk Factors                   │
│ ▪ iPhone      52%                1. Supply chain dependencies        │
│ ▪ Services    22%                2. Regulatory scrutiny (EU/US)      │
│ ▪ Mac          8%                3. FX headwinds                     │
├──────────────────────────────────────────────────────────────────────┤
│  [ Ask Deeper Questions (Chat Interface) ]                           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 5. Multi-Company Comparison Engine

**Goal:** Compare two companies head-to-head using TradingView price overlays, visual bar charts, and LLM text analysis.

- **Pipeline Check:** Check `finsight:filings` for all requested tickers. Trigger standard ingestion for any missing tickers before proceeding.
- **LLM Text Analysis:** Pass both 10-K contexts to the LLM to generate Financial Head-to-Head, Pros & Cons, Strategic Positioning, and a Final Verdict.

### Comparison UI Layout
```text
┌──────────────────────────────────────────────────────────────────────┐
│  Comparing: Apple Inc (AAPL)  vs  Microsoft Corp (MSFT)              │
├──────────────────────────────────────────────────────────────────────┤
│  [ TradingView Multi-Symbol Chart: AAPL & MSFT Price Overlay ]       │
├───────────────────────┬──────────────────────────────────────────────┤
│   Financial Metrics   │       LLM Comparative Analysis               │
│  [ Bar Chart: Rev ]   │ 📈 Financial Head-to-Head: MSFT showing      │
│  [ Bar Chart: NI  ]   │    faster cloud growth, AAPL leads FCF...    │
│                       │                                              │
│  AAPL Margin: 45.2%   │ ⚖️ Pros & Cons:                              │
│  MSFT Margin: 69.8%   │    AAPL: Ecosystem lock-in                   │
│                       │    MSFT: Enterprise AI dominance             │
│                       │                                              │
│                       │ 🎯 Verdict: MSFT holds stronger momentum...  │
└───────────────────────┴──────────────────────────────────────────────┘
```

---

## 6. Files to Build

### Backend
```text
backend/
├── cache/
│   ├── redis_client.py       ← Redis connection singleton
│   ├── ticker_cache.py       ← load_tickers, search_tickers
│   └── filing_registry.py    ← is_ingested, register_filing
├── services/
│   ├── dashboard.py          ← Metric & Executive summary extraction
│   └── comparison.py         ← Multi-company LLM extraction
├── api/
│   └── routes.py             ← New endpoints
└── jobs/
    └── refresh_tickers.py    ← Daily 2am refresh
```

### Frontend
```text
frontend/src/
├── components/
│   ├── CompanySearch.jsx     ← Dropdown with compare mode toggle
│   ├── Dashboard.jsx         ← Main dashboard + TradingView widget
│   ├── CompareView.jsx       ← Recharts bar charts + Text comparison
│   └── FilingPanel.jsx       ← Existing chat interface
└── App.jsx                   
```

---

## 7. API Endpoints

- **`GET /api/companies/search?q={query}`**: Returns `[{name, ticker, cik}]` using pure Redis filtering. Zero API calls.
- **`GET /api/companies/{ticker}/info`**: `HGET finsight:tickers {ticker}`
- **`POST /api/companies/{ticker}/ingest`**: Checks registry. If missing, triggers EDGAR fetch → chunk → Qdrant → metrics → Redis.
- **`GET /api/companies/{ticker}/dashboard`**: Reads `finsight:dashboard:{ticker}` from Redis.
- **`POST /api/companies/compare`**: Payload: `{ "tickers": ["AAPL", "MSFT"] }`. Validates ingestion, generates LLM comparative report, caches under `finsight:compare:{t1}_{t2}`.
- **`POST /api/admin/refresh-tickers`**: Manually triggers the 2am cron job.

---

## 8. Backend Implementation Details

### Ticker Cache (`backend/cache/ticker_cache.py`)
```python
import json, httpx
from config import get_settings

TICKERS_KEY = "finsight:tickers"
SEC_URL = "https://www.sec.gov/files/company_tickers.json"

async def load_tickers_into_redis(redis_client) -> int:
    headers = {"User-Agent": get_settings().SEC_EDGAR_USER_AGENT}
    async with httpx.AsyncClient() as client:
        resp = await client.get(SEC_URL, headers=headers)
        data = resp.json()

    pipe = redis_client.pipeline()
    for entry in data.values():
        ticker = entry["ticker"].upper()
        record = json.dumps({
            "name": entry["title"],
            "ticker": ticker,
            "cik": str(entry["cik_str"]).zfill(10),
        })
        pipe.hset(TICKERS_KEY, ticker, record)
    pipe.execute()
    return len(data)

def search_tickers(redis_client, query: str, limit: int = 8) -> list[dict]:
    query = query.upper().strip()
    all_entries = redis_client.hgetall(TICKERS_KEY)
    
    ticker_matches, name_matches = [], []
    for ticker_key, json_str in all_entries.items():
        record = json.loads(json_str)
        if ticker_key.startswith(query): ticker_matches.append(record)
        elif query in record["name"].upper(): name_matches.append(record)
    
    return (ticker_matches + name_matches)[:limit]
```

### Filing Registry (`backend/cache/filing_registry.py`)
```python
import json
from datetime import datetime, timezone

REGISTRY_KEY = "finsight:filings"

def is_ingested(redis_client, ticker: str) -> bool:
    return bool(redis_client.hexists(REGISTRY_KEY, ticker.upper()))

def register_filing(redis_client, ticker: str, filing_id: str, meta: dict):
    record = json.dumps({
        "filing_id": filing_id,
        "chunk_count": meta.get("chunk_count", 0),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    })
    redis_client.hset(REGISTRY_KEY, ticker.upper(), record)
```

### Dashboard Extraction Setup (`backend/services/dashboard.py`)
Prompt the LLM (Haiku) to extract structured metrics AND an `executive_summary`:
```python
METRICS_TO_EXTRACT = [
    "executive_summary",          # 2-3 paragraph holistic overview
    "revenue_latest_year",        # e.g., "$383B"
    "revenue_yoy_change",         # e.g., "+2.9%"
    "net_income_latest_year", 
    "gross_margin_pct",
    "top_3_risk_factors",         # Array of strings
    "primary_revenue_segments",   # Array of strings
]
```

### FastApi Lifespan (`backend/main.py`)
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = get_redis()
    if not redis.exists(TICKERS_KEY):
        await load_tickers_into_redis(redis)
        
    scheduler = AsyncIOScheduler()
    scheduler.add_job(refresh_ticker_index, "cron", hour=2, args=[redis])
    scheduler.start()
    yield
    scheduler.shutdown()
```

---

## 9. Docker Compose Update

```yaml
# Add to docker-compose.yml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
  command: redis-server --appendonly yes
  restart: unless-stopped

# Add to backend requirements.txt:
# redis>=5.0.0
# apscheduler>=3.10.0
```

---

## 10. Final Build Order

1. **Redis Foundation:** Setup `redis_client.py`, `ticker_cache.py`, and `filing_registry.py`. Wire into `main.py` lifespan.
2. **Core API & Ingestion:** Build the search endpoint and the single-company `POST /api/companies/{ticker}/ingest` pipeline.
3. **Enhanced Dashboard Extraction:** Build `services/dashboard.py` to extract metrics **plus** the `executive_summary`. Create `GET /api/companies/{ticker}/dashboard`.
4. **Main Page UI & TradingView:** Build the React frontend to display the Dashboard view, embedding the TradingView Advanced Widget above the Executive Summary.
5. **Comparison Engine (Backend):** Create the `POST /api/companies/compare` endpoint, incorporating multi-ticker ingestion validation and the LLM comparative prompt.
6. **Comparison Engine (Frontend):** Build the "Compare" UI allowing multi-selection, rendering the Recharts bar charts, Multi-Symbol TradingView chart, and the LLM text report.
