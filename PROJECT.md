# FinSight AI Project Context

> Drop this file into any AI coding session (Cursor, Claude Code, Gemini Code Assist, Copilot, etc.) so the AI understands the full project context immediately. No re-explaining.
> 

---

## What Is This Project

**FinSight AI** is a Financial Risk Intelligence Platform that analyses SEC EDGAR 10-K filings using a multi-agent RAG system. It extracts risk factors, financial metrics, and generates structured risk reports — demonstrating production-grade AI engineering.

---

## Why It Exists

Portfolio project for Kural's transition from Senior Software Engineer to AI Engineer. Built to demonstrate:

- Multi-agent RAG architecture (not a toy chatbot)
- Production observability (LangFuse tracing, RAGAS evals)
- Real data (SEC EDGAR — not synthetic)
- End-to-end ownership (infra → agents → evaluation → deployment)

---

## Current State

- **Day 1 of 100**
- Hello World FastAPI app — being Dockerised right now
- No agents yet, no RAG yet, no vector DB yet
- This is the foundation — everything gets built on top of this

---

## Target Architecture (by Day 70)

```
┌─────────────────────────────────────────────────────┐
│                    FinSight AI                      │
├─────────────────────────────────────────────────────┤
│  FastAPI (REST + GraphQL)  ←→  LangGraph Workflow   │
├──────────────┬──────────────────────────────────────┤
│  Agent Crew (CrewAI)                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐│
│  │Researcher│ │ Analyst  │ │   Report Writer      ││
│  └──────────┘ └──────────┘ └──────────────────────┘│
├──────────────┬──────────────────────────────────────┤
│  Qdrant (hybrid search: BM25 + dense)               │
│  SEC EDGAR 10-K filing chunks                       │
├──────────────┬──────────────────────────────────────┤
│  LangFuse (tracing) + RAGAS (evals) + PostHog       │
├──────────────┬──────────────────────────────────────┤
│  Redis (cache) + Celery (async tasks)               │
├──────────────┬──────────────────────────────────────┤
│  Docker → GCP Cloud Run (live public URL)           │
└─────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| API | FastAPI + Pydantic + strawberry-graphql |
| LLM | Anthropic Claude (primary) + OpenAI (fallback) |
| Agents | LangGraph + CrewAI + Pydantic AI |
| RAG | Qdrant (hybrid: BM25 + dense) + sentence-transformers |
| LLMOps | LangFuse + RAGAS + LangSmith |
| Analytics | PostHog |
| Security | presidio-analyzer + guardrails-ai |
| Async | Celery + Redis |
| Containerisation | Docker + docker-compose |
| Cloud | GCP Cloud Run + Artifact Registry |
| Data | SEC EDGAR API + pypdf + httpx |

---

## Project Structure (target)

```
finsight-ai/
├── CLAUDE.md              ← AI context (this repo)
├── PROJECT.md             ← Project context
├── SKILLS.md              ← Developer skills reference
├── docker-compose.yml     ← All services
├── Dockerfile             ← App container
├── requirements.txt
├── .env.example
├── app/
│   ├── main.py            ← FastAPI entry point
│   ├── api/               ← Route handlers
│   ├── agents/            ← LangGraph + CrewAI agents
│   ├── rag/               ← RAG pipeline + vector store
│   ├── ingestion/         ← SEC EDGAR fetcher + chunker
│   ├── evaluation/        ← RAGAS eval scripts
│   ├── security/          ← Input validation + PII filtering
│   └── models/            ← Pydantic schemas
├── tests/
│   ├── eval_baseline/     ← 10 hand-curated Q&A pairs (Week 2)
│   └── unit/
└── infra/
    └── gcp/               ← Cloud Run deployment config
```

---

## Coding Standards

- **Language:** Python 3.11+
- **Style:** PEP8, type hints everywhere, Pydantic for all data models
- **Async:** Use `async/await` for all I/O operations
- **Error handling:** Never silent failures — log everything, return structured errors
- **Docker:** Everything runs in Docker. If it doesn't work in Docker, it doesn't count.
- **Commits:** Conventional commits (`feat:`, `fix:`, `chore:`, `docs:`)
- **Tests:** Write tests for agent outputs. RAGAS eval set is the regression suite.

---

## Key Constraints

- **Token efficiency:** Developer uses Graphify — keep AI responses dense and structured
- **Production mindset:** Treat this like Wiglaf (Barclays). Versioning, monitoring, structured errors.
- **No hallucination:** RAG answers must be grounded in SEC data with citations
- **Cost tracking:** Every LLM call must log model used, tokens in/out, cost estimate
- **GDPR aware:** EU deployment — no PII stored without consent

---

## Evaluation Baseline (Week 2 task)

10 hand-curated Q&A pairs on SEC 10-K filings. Run every week to track quality regression.

Location: `tests/eval_baseline/questions.json`

Format:

```json
[
  {
    "question": "What are Apple's top 3 risk factors in their 2023 10-K?",
    "expected_topics": ["supply chain", "competition", "regulation"],
    "source_filing": "AAPL_10K_2023"
  }
]
```

---

## Milestones

| Day | Milestone |
| --- | --- |
| 1 | Hello World FastAPI + Dockerised ✅ (today) |
| 7 | SEC EDGAR ingestion + basic LLM Q&A |
| 14 | RAG pipeline + eval baseline (10 Q&A pairs) |
| 21 | Entity extraction (NER → structured JSON) |
| 28 | First agent (Pydantic AI, type-safe) |
| 35 | LangGraph multi-step workflow |
| 42 | CrewAI agent crew (3 roles) + security layer |
| 49 | LangFuse tracing + RAGAS evals |
| 51–55 | 🏅 CCA Exam |
| 56 | Qdrant hybrid search |
| 63 | Model routing + cost dashboard |
| 70 | 🚀 FinSight AI LIVE on GCP Cloud Run |
| 77 | LoRA/QLoRA fine-tuning experiment |
| 84 | GraphRAG layer |
| 91 | Portfolio polished + LinkedIn posts |
| 92–100 | 15 applications + interviews + offer 🎯 |

---

## Resources

- **100-day roadmap:** [Notion](https://www.notion.so/100-Day-AI-Engineer-Roadmap-Kural-34bc0be3471481f289addc0e411316d5?pvs=21)
- **SEC EDGAR API:** https://www.sec.gov/cgi-bin/browse-edgar
- **CCA Exam prep:** https://claudecertifications.com
- **LangGraph docs:** https://langchain-ai.github.io/langgraph/
- **Qdrant docs:** https://qdrant.tech/documentation/