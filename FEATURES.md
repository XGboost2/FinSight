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
| ✅ Qdrant vector store | `rag/retriever.py` | Dense cosine similarity, `query_points` API, filing-scoped filters |
| ✅ RAG Q&A pipeline | `rag/pipeline.py` | ingest + retrieve orchestration |
| ✅ Multi-provider LLM routing | `services/llm.py` | DeepSeek primary → Claude → OpenAI → mock. Smart router by query complexity |
| ✅ Model selector UI | `FilingPanel.jsx` | 8-model pill selector, per-request override |
| ✅ XBRL financial parser | `ingestion/xbrl.py` | Deterministic revenue, income, margin, YoY from SEC EDGAR XBRL API |
| ✅ Dashboard metrics | `services/dashboard.py` | XBRL for numbers + LLM for narrative, Redis 7d cache |
| ✅ Company comparison | `services/comparison.py` | Two-ticker LLM head-to-head + YoY revenue trend |
| ✅ Redis ticker cache | `cache/ticker_cache.py` | ~13k SEC-registered companies, O(1) lookup |
| ✅ Filing registry | `cache/filing_registry.py` | Ingestion gate, Redis hash, force re-ingest |
| ✅ REST API | `api/routes.py` | Ingest, chat, search, dashboard, compare, health |
| ✅ React frontend | `frontend/src/` | Search, dashboard, compare, filing chat panel |
| ✅ TradingView charts | `Dashboard.jsx`, `CompareView.jsx` | Live price charts, dual compare charts |
| ✅ Redis + Qdrant status dots | `StatusDots.jsx` | Polls `/api/health` every 30s |
| ✅ Rotating file logger | `logging_config.py` | `backend/logs/finsight.log`, 10MB × 5 |
| ✅ Unit tests (backend) | `tests/test_routes.py` | pytest, 25 tests, all endpoints mocked |
| ✅ Unit tests (frontend) | `src/components/__tests__/` | vitest + RTL, all 5 components |

---

## Feature Backlog — Priority Order

---

### 0. Comprehensive 10-K Analysis Report
**Priority: HIGHEST — the core product, everything else feeds into this**

Generate a structured, data-driven fundamental analysis report for any company from its 10-K filing. Equivalent in depth and format to a professional equity research note. The chatbox sits below it — users read the report, then drill into specifics via Q&A.

This is the primary output the CrewAI agents (Feature 3) produce. Build the report format and UI first using existing data (XBRL + RAG), then wire the agents in later.

---

#### Report Sections

**1. Company Overview**
- Business description (RAG from Item 1)
- Key revenue segments and primary markets
- Filing period and fiscal year end

**2. Financial Performance** ← XBRL (deterministic)
- Revenue, Net Income, Gross Profit, Operating Income
- EPS, Free Cash Flow (where available in XBRL)
- YoY change for each metric

**3. Trend Analysis**
- Revenue trend across last 3 years (XBRL multi-year)
- Margin expansion or compression narrative
- Segment performance breakdown

**4. Detailed Findings Table** ← core of the report
| Category | Metric | Value | YoY | Signal | Interpretation |
|----------|--------|-------|-----|--------|----------------|
| Revenue | Total Revenue | $383B | -2.8% | ⚠️ | Hardware softness... |
| Profitability | Net Income | $97B | +4.2% | ✅ | Cost efficiency... |
| Profitability | Gross Margin | 44.1% | +0.8pp | ✅ | Services mix shift... |
| Profitability | Operating Margin | 29.8% | +1.1pp | ✅ | Opex discipline... |
| Risk | Risk Score | 0.34/1.0 | — | 🟡 | Regulatory + supply chain |
| Sentiment | MD&A Tone | 0.68 Positive | +0.03 | ✅ | Management confident |
| Events | Recent 8-Ks | 2 filed | — | ℹ️ | Earnings + legal |

Signals: ✅ Positive · ⚠️ Caution · 🔴 Negative · ℹ️ Neutral

**5. Risk Assessment**
- Risk Score: X.XX / 1.0 (Low / Moderate / High)
- Top 3 risk factors from Item 1A (LLM-extracted, concise)
- Recent material events from 8-K (when available)
- YoY risk diff summary — new risks flagged (Feature 1)

**6. Management Sentiment**
- FinBERT score on MD&A: X.XX (Positive / Neutral / Negative)
- YoY sentiment trend if prior year available
- Key themes from management discussion (2-3 sentences)

**7. Bull Case** ← 3-5 bullets, grounded in filing data with citations
**8. Bear Case** ← 3-5 bullets, grounded in filing data with citations
**9. Verdict** ← 2-3 sentence balanced conclusion with risk score

---

#### Pydantic Output Model

```python
class SignalType(str, Enum):
    POSITIVE = "positive"
    CAUTION = "caution"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"

class FindingRow(BaseModel):
    category: str
    metric: str
    value: str
    yoy: str | None
    signal: SignalType
    interpretation: str

class AnalysisReport(BaseModel):
    ticker: str
    company_name: str
    fiscal_year: str
    generated_at: datetime
    # Sections
    company_overview: str
    financial_summary: dict          # XBRL data
    trend_narrative: str
    findings_table: list[FindingRow]
    risk_score: float                # 0.0 → 1.0
    risk_factors: list[str]          # top 3, concise
    sentiment_score: float           # FinBERT 0.0 → 1.0
    sentiment_label: str             # Positive / Neutral / Negative
    management_themes: str
    bull_case: list[str]             # 3-5 bullets
    bear_case: list[str]             # 3-5 bullets
    verdict: str
    citations: list[dict]            # source + filing section for each claim
```

---

#### Data sources per section

| Section | Source | Module |
|---------|--------|--------|
| Financial metrics | XBRL | `ingestion/xbrl.py` ✅ built |
| Revenue trend | XBRL multi-year | `ingestion/xbrl.py` ✅ built |
| Company overview | RAG on Item 1 | `rag/pipeline.py` ✅ built |
| Risk factors | RAG on Item 1A | `rag/pipeline.py` ✅ built |
| Risk score | LLM scoring | `services/sentiment.py` (Feature 2) |
| Management sentiment | FinBERT on Item 7 | `services/sentiment.py` (Feature 2) |
| Bull/Bear case | CrewAI agents | Feature 3 |
| YoY risk diff | Diff engine | Feature 1 |
| 8-K events | EDGAR 8-K | Feature 3b |

**Note:** Build the report with available data now (XBRL + RAG already built). Add FinBERT, agents, and 8-K as those features land — the report format stays the same, sections just get richer.

---

#### API endpoint
```
GET /api/companies/{ticker}/report    → full AnalysisReport JSON
```
Redis cached with 24h TTL. Regenerate with `?refresh=true`.

---

#### Frontend — Report Page

New `ReportView.jsx` component (or full page route):
- Replaces the current simple Dashboard metrics cards
- Rendered as a structured document (think Bloomberg terminal meets readable prose)
- Findings table with colour-coded signal badges
- Bull/Bear cards side by side
- Risk score gauge (0.0 → 1.0)
- Sentiment score badge
- Chatbox below — pre-loaded with the report as context so questions are grounded

**User flow:**
```
Search company → Load report (10-15s first time, instant from cache)
→ Read comprehensive analysis
→ Ask follow-up questions in chatbox
→ LLM answers grounded in both the report AND the raw filing chunks
```

---

### 1. YoY Risk Factor Diff — highlight what changed year-over-year
**Priority: HIGH — strong differentiator, unique to FinSight**

Compare Item 1A (Risk Factors) text between current 10-K and prior year. New paragraphs = new threats. Removed = resolved risks. Changed = evolving concerns.

**What to build:**
- `ingestion/edgar.py` — extend to fetch prior year 10-K
- `services/diff.py` — paragraph-level diff using `difflib.SequenceMatcher` + BGE embeddings for semantic matching
- Classify each paragraph: `new` | `removed` | `changed` | `unchanged`
- `DiffResponse` Pydantic model

**API endpoint:**
```
GET /api/companies/{ticker}/risk-diff?years=2
```

**Frontend:** `RiskDiff.jsx` — added paragraphs green, removed red, changed highlighted inline.

**Note:** Use BGE embeddings (already loaded) to match semantically similar paragraphs before string diff — handles minor rewording that isn't a real change.

---

### 2. FinBERT Sentiment per Section — tone analysis
**Priority: HIGH — strong ML portfolio story**

Apply FinBERT to score MD&A section sentiment (positive / negative / neutral). Track trend across filing years to show if management language is becoming more cautious.

**What to build:**
- `services/sentiment.py` — `ProsusAI/finbert` via `transformers` pipeline
- Run on Item 7 chunks only (~10-20 chunks), batch inference, aggregate per section
- Cache in Redis (`sentiment:{filing_id}`, 30d TTL)

**API endpoint:**
```
GET /api/companies/{ticker}/sentiment
```

**Frontend:** Sentiment badge on dashboard + trend sparkline if multi-year data available.

**Note:** Don't run on full filing. Item 7 only. CPU inference <5s. 110M model, no GPU needed.

**Requirements to add:**
```
transformers>=4.40.0
torch>=2.0.0  # cpu only
```

---

### 3. Multi-Source Intelligence + CrewAI Agents + LangGraph + MCP
**Priority: HIGH — core agentic AI feature, inspired by TradingAgents architecture**

Expand from single 10-K RAG to a full multi-source intelligence pipeline. Inspired by [TradingAgents](https://github.com/TauricResearch/TradingAgents) (Dec 2024 paper) — adapted for fundamental analysis rather than trading signals.

**Key patterns borrowed from TradingAgents:**
- Parallel analyst team (each agent specialises in one data source)
- Bull/Bear researcher debate → balanced, trustworthy output
- Tiered LLM selection (cheap model for data retrieval, power model for reasoning)
- ReAct prompting on all agents (Reason → Act → Observe loop)
- Risk Manager as final quality gate

---

#### 3a. News Ingestion
- `ingestion/news.py` — Alpha Vantage `NEWS_SENTIMENT` endpoint (key already in config)
- Returns: title, summary, URL, published_at, sentiment score per ticker
- Embed summaries with BGE, store in Qdrant `news` collection (1hr Redis cache)

**API endpoint:**
```
GET /api/companies/{ticker}/news
```
**Qdrant collection:** `news` — payload: `{ticker, headline, summary, url, published_at, sentiment}`

---

#### 3b. Additional Filing Types — 10-Q and 8-K

**10-Q (Quarterly Report)**
- `fetch_and_extract(ticker, "10-Q")` — same pipeline as 10-K, fetch last 3 quarters
- Store in `filings` collection with `filing_type: "10-Q"` in payload
- XBRL works for 10-Q too — quarterly revenue, income, margins

**8-K (Material Events)**
- Fetch last 90 days of 8-Ks per ticker
- Tag event type in payload: `earnings | leadership_change | acquisition | legal | guidance`
- Separate Qdrant collection `events` (30d TTL — events go stale)

**API endpoints:**
```
GET /api/companies/{ticker}/filings              → all ingested filings
GET /api/companies/{ticker}/events               → recent 8-K events with type tags
POST /api/companies/{ticker}/ingest?types=10-K,10-Q,8-K
```

---

#### 3c. CrewAI Agent Crew — 7 Roles

Adapted from TradingAgents' firm structure. FinSight uses analysis roles, not trading execution roles.

```
agents/
├── fundamentals_analyst.py   ← EDGAR filings + XBRL
├── news_analyst.py           ← Alpha Vantage news
├── sentiment_analyst.py      ← FinBERT scores on MD&A + news
├── risk_analyst.py           ← Item 1A risk factors + 8-K events
├── bull_researcher.py        ← argues positive case from analyst reports
├── bear_researcher.py        ← argues downside/risk case
└── report_writer.py          ← synthesises debate into final report
```

```python
# Analyst Team — run in parallel, cheap model (deepseek-chat)
fundamentals_analyst = Agent(
    role="Fundamentals Analyst",
    goal="Extract and interpret financial metrics from SEC filings",
    backstory="CFA-level analyst specialising in SEC regulatory documents",
    tools=[FetchFilingTool(), FetchQuarterlyTool(), GetXBRLMetricsTool(), SearchFilingsTool()],
    llm=cheap_llm,   # deepseek-chat for data retrieval
)

news_analyst = Agent(
    role="News Analyst",
    goal="Find recent news and assess market impact for a company",
    backstory="Market intelligence analyst tracking financial news and events",
    tools=[FetchNewsTool(), FetchEventsTool(), SearchNewsTool()],
    llm=cheap_llm,
)

sentiment_analyst = Agent(
    role="Sentiment Analyst",
    goal="Score management tone from MD&A and assess news sentiment trends",
    backstory="NLP specialist measuring market and management sentiment signals",
    tools=[GetMDASentimentTool(), GetNewsSentimentTool()],
    llm=cheap_llm,
)

risk_analyst = Agent(
    role="Risk Analyst",
    goal="Identify and prioritise material risks from filings and recent events",
    backstory="Risk management specialist focused on regulatory and operational risk",
    tools=[ExtractRiskFactorsTool(), GetMaterialEventsTool(), GetYoYRiskDiffTool()],
    llm=cheap_llm,
)

# Research Team — sequential, power model (deepseek-reasoner)
bull_researcher = Agent(
    role="Bull Researcher",
    goal="Build the strongest possible positive case from analyst reports",
    backstory="Growth-focused analyst who finds opportunity in data",
    tools=[],   # operates on analyst reports only, no raw data access
    llm=power_llm,  # deepseek-reasoner for reasoning
)

bear_researcher = Agent(
    role="Bear Researcher",
    goal="Challenge assumptions and identify risks the bull case ignores",
    backstory="Risk-focused analyst who stress-tests every investment thesis",
    tools=[],
    llm=power_llm,
)

report_writer = Agent(
    role="Report Writer",
    goal="Synthesise the bull/bear debate into a balanced, grounded analysis report",
    backstory="Senior analyst who produces clear, cited, actionable research",
    tools=[],
    llm=power_llm,
)
```

**LLM tier assignment (from TradingAgents):**
- Analyst agents → `deepseek-chat` (data retrieval, low reasoning needed, cheap)
- Researcher + Report Writer → `deepseek-reasoner` (complex multi-step reasoning)

---

#### 3d. LangGraph Orchestrator

`agents/graph.py` — `StateGraph` with full TradingAgents-style workflow:

```python
class AnalysisState(TypedDict):
    ticker: str
    question: str
    fundamentals_report: str
    news_report: str
    sentiment_report: str
    risk_report: str
    bull_case: str
    bear_case: str
    debate_rounds: int
    final_report: str
    risk_score: float   # 0.0 (low risk) → 1.0 (high risk)
    citations: list[dict]
```

**Graph nodes:**
```
route          → classify query, decide which analysts are needed
   ↓
[parallel via Send()]
fundamentals_node  news_node  sentiment_node  risk_node
   ↓                  ↓            ↓              ↓
   └──────────────────┴────────────┴──────────────┘
                       ↓
               bull_research_node
                       ↓ (N debate rounds)
               bear_research_node
                       ↓
               report_writer_node
                       ↓
               risk_manager_node   ← final risk score + red flags
                       ↓
                    output
```

**Debate mechanic (from TradingAgents):**
- Bull and Bear researchers exchange N rounds (default 2)
- Each round, bear challenges bull's latest argument with specific counter-evidence
- Report Writer reads full debate transcript → balanced verdict

**ReAct prompting on all agents:**
- Every agent prompt includes: `Thought: ... Action: ... Observation: ...` loop
- Agents can call tools multiple times before producing their report

---

#### 3e. MCP Servers

```
mcp/
├── edgar_server.py   → tools: fetch_10k, fetch_10q, fetch_8k, search_filings, get_xbrl
└── news_server.py    → tools: get_news, get_sentiment, search_news_by_topic
```

Claude calls these as native MCP tools — LLM decides which to invoke per question without explicit routing logic.

---

**Full flow — complete picture:**
```
User: "Is Apple a good investment right now?"
      ↓
LangGraph router → parallel analyst team:
  Fundamentals Analyst      News Analyst         Sentiment Analyst    Risk Analyst
  → 10-K + 10-Q + XBRL     → Alpha Vantage      → FinBERT on MD&A    → Item 1A risks
  → revenue trends          → recent articles    → mgmt tone score    → 8-K events
      ↓                          ↓                    ↓                    ↓
  [fundamentals_report]  [news_report]       [sentiment_report]   [risk_report]
      └──────────────────────┴────────────────────┴────────────────────┘
                                   ↓
                    Bull Researcher ↔ Bear Researcher (2 rounds)
                                   ↓
                            Report Writer
                                   ↓
                           Risk Manager (risk_score: 0.34)
                                   ↓
  "Apple shows strong fundamentals (revenue +5% QoQ per 10-Q), positive
   management sentiment, but faces new regulatory risk (8-K Oct 3) and
   bearish analyst commentary. Risk score: 0.34/1.0 (moderate)."
```

**Why this is a strong portfolio demo:**
- Shows 7 specialised agents with clear roles — explains itself in an interview
- Bull/Bear debate produces trustworthy, balanced output vs single LLM answer
- Risk score is a quantified, actionable output
- Tiered LLM usage = documented cost savings story for LangFuse

**Requirements to add:**
```
crewai>=0.70.0
langgraph>=0.2.0
mcp>=1.0.0
```

---

### 4. Multi-Filing RAG — query across multiple years
**Priority: HIGH — extends agent infrastructure from Feature 3**

Query across 3+ years of a company's filings. Builds directly on the LangGraph infrastructure added in Feature 3.

**What to build:**
- `ingestion/edgar.py` — fetch N most recent 10-Ks per ticker
- `rag/retriever.py` — `search_multi()` using `MatchAny` filter across multiple `filing_id`s
- Extend `agents/graph.py` — add multi-filing retrieval branch with per-filing citation

**API endpoint:**
```
POST /api/companies/{ticker}/multi-chat    → cross-filing RAG answer
```

**Example queries unlocked:**
- "How have Apple's risk factors changed over 3 years?"
- "When did management first mention AI as a risk?"
- "Show revenue trend 2021–2023"

---

### 5. Segment Benchmarking — compare business segments
**Priority: MEDIUM — builds on XBRL parser (already done)**

Extract segment revenue from XBRL (`us-gaap/SegmentReportingInformationRevenue`). Compare iPhone vs Azure vs AWS side by side.

**What to build:**
- Extend `ingestion/xbrl.py` — segment revenue extraction
- `services/segments.py` — LLM-assisted label normalisation across companies
- Extend `CompareResponse` with segment data

**API endpoint:**
```
GET /api/companies/{ticker}/segments
POST /api/companies/compare-segments
```

---

### 6. Competitor Extraction — competitor graph from Item 1
**Priority: MEDIUM — good visual, quick win**

Extract competitor names from Item 1 using NER. Build a graph of who considers whom a rival.

**What to build:**
- `services/competitors.py` — spaCy ORG entity extraction from Item 1 text
- Match names to SEC tickers via Redis ticker cache
- Store in Redis (`competitors:{filing_id}`)

**API endpoint:**
```
GET /api/companies/{ticker}/competitors
```

**Frontend:** `CompetitorGraph.jsx` — force-directed D3 graph. Click a node → load that company's dashboard.

**Requirements to add:**
```
spacy>=3.7.0
```

---

## Infrastructure Backlog

| Feature | Priority | Notes |
|---------|----------|-------|
| 📋 Hybrid BM25 + dense search | HIGH | Qdrant sparse vectors, better exact-term retrieval for financial jargon |
| 📋 LangFuse tracing | HIGH | Wire every LLM + agent call — cost and latency dashboard |
| 📋 RAGAS eval baseline | HIGH | 10 Q&A pairs in `tests/eval_baseline/questions.json`, run weekly |
| 📋 PII filtering (presidio) | MEDIUM | GDPR — filter outputs before returning to frontend |
| 📋 GCP Cloud Run deployment | MEDIUM | Target Day 70 |
| 💡 Merge dashboard + report cache | LOW | `finsight:dashboard:*` is a subset of `finsight:report:*`. Once agents (Feature 3) make the report the primary output, drop the dashboard cache and read metric cards from `report.financial_data` instead. One Redis key, one LLM call. |
| 💡 Form 4 insider trading | LOW | Executive buy/sell signals — supplementary, interpret with caution |
| 💡 DEF 14A proxy statement | LOW | Exec comp vs performance — low demo ROI, build last |
| 💡 GraphQL endpoint | LOW | strawberry-graphql for flexible frontend queries |
| 💡 Celery async tasks | LOW | Move ingest to background task queue |
| 💡 FinE5 embeddings | LOW | `FinanceMTEB/FinE5` — 7B, needs GPU, upgrade path only |

---

## Implementation Order (recommended)

```
Week 3:     ✅ XBRL parsing — DONE
Week 4:     Comprehensive Report — AnalysisReport model + API + ReportView UI (Feature 0)
            → Build with existing XBRL + RAG data, stubs for FinBERT/agents sections
Week 4-5:   YoY Risk Factor Diff → plugs into report risk section (Feature 1)
Week 5:     FinBERT sentiment → plugs into report sentiment section (Feature 2)
            → Report now has live risk score + sentiment badge
Week 5-6:   News ingestion + 10-Q + 8-K ingestion (Feature 3a + 3b)
            → Report gains events section + quarterly data
Week 6:     CrewAI analyst team — 4 parallel analysts (Feature 3c)
            → Report bull/bear sections now agent-generated
Week 6-7:   Bull/Bear debate + Report Writer + Risk Manager (Feature 3c cont.)
Week 7:     LangGraph orchestrator — full StateGraph with ReAct (Feature 3d)
Week 7:     MCP servers — EDGAR MCP + News MCP (Feature 3e)
Week 7-8:   Multi-filing RAG — cross-year questions in chatbox (Feature 4)
Week 8:     Segment benchmarking (Feature 5)
Week 8:     Competitor extraction (Feature 6)
Week 8-9:   LangFuse tracing + RAGAS eval baseline
Week 10:    GCP Cloud Run deployment
```

---

## Key Technical Decisions (locked)

- **Embeddings:** `fastembed` + `BAAI/bge-base-en-v1.5` (ONNX, CPU, 768-dim) — no torch in Docker
- **Vector DB:** Qdrant — `filings` collection (10-K) + `news` collection (articles)
- **LLM:** DeepSeek primary → Claude → OpenAI. Smart router by query complexity
- **Agents:** 7 CrewAI roles (4 analysts + bull + bear + report writer). LangGraph orchestrates the StateGraph
- **LLM tiers:** `deepseek-chat` for analyst data retrieval · `deepseek-reasoner` for bull/bear debate + synthesis
- **ReAct prompting:** Thought → Action → Observation loop on all agents
- **MCP:** EDGAR + News exposed as MCP servers, Claude calls them as native tools
- **Cache:** Redis — LLM responses + news (1hr TTL) + dashboard (7d TTL)
- **FinBERT runs CPU** — Item 7 only, batch inference, no GPU needed
- **XBRL over LLM extraction** — deterministic numbers always preferred

---

## Embedding Upgrade Path (future, not now)

| Model | Size | GPU needed | When |
|-------|------|-----------|------|
| `BAAI/bge-base-en-v1.5` (current) | 90MB ONNX | No | Now |
| `BAAI/bge-large-en-v1.5` | 300MB ONNX | No | When quality needs improvement |
| `FinanceMTEB/FinE5` | ~14GB | Yes | GCP deployment with GPU |
