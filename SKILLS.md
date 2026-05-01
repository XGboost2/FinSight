# SKILLS.md — Developer Skill Reference

> This file tells AI coding assistants (Claude Code, Cursor, Copilot, Gemini)
> exactly what the developer knows so responses are calibrated correctly.
> Don't explain basics covered under "Expert". Do explain things under "Learning".

---

## Developer: Kural
Senior Software Engineer transitioning to AI Engineer.
7 years Python/backend. Now on Day 1 of a 100-day AI engineering upskill.

---

## Expert Level — Skip basics entirely

| Skill | Depth |
|-------|-------|
| Python | Flask, async/await, decorators, packaging, type hints, testing |
| REST API design | Auth, versioning, request/response patterns, FastAPI |
| Docker | Dockerfile, docker-compose, multi-stage builds, networking |
| Celery + Redis | Task queues, async patterns, caching, beat scheduler |
| PostgreSQL | Query optimisation, indexing, CTEs, JSONB, migrations |
| Git / GitHub | Branching, PRs, conventional commits, CI/CD |
| Linux / Bash | File ops, scripting, cron, environment management |
| Pydantic | Models, validators, settings, nested schemas |
| ML pipelines | scikit-learn, PyCaret, Keras — training + deployment |
| Production ops | Versioning discipline, monitoring, structured logging |

---

## Intermediate Level — Some context useful, skip absolute basics

| Skill | Notes |
|-------|-------|
| FastAPI | Dependency injection, background tasks, middleware |
| AWS | EC2, S3, IAM — surface level only |
| Kafka | Pub/sub concepts, producer/consumer — not production experience |
| React / TypeScript | Can read and modify — not primary strength |
| SQL advanced | Window functions, partitioning — knows concepts |

---

## Currently Learning — Treat as beginner-to-intermediate

Explain concepts clearly. Show working code examples. Connect to FinSight AI use cases.

| Skill | Current Level | Week in Plan |
|-------|--------------|--------------|
| LLM APIs (Anthropic, OpenAI) | Day 1 — Hello World | Week 1 |
| Prompt engineering | Starting | Week 1 |
| Structured outputs / function calling | Starting | Week 1–4 |
| RAG + vector databases | Not started | Week 2 |
| LangChain | Not started | Week 2 |
| Pydantic AI | Not started | Week 4 |
| LangGraph | Not started | Week 5 |
| MCP (Model Context Protocol) | Concept aware | Week 5 |
| CrewAI | Not started | Week 6 |
| Guardrails / security layer | Not started | Week 6 |
| LLMOps — LangFuse, RAGAS | Not started | Week 7 |
| Qdrant (advanced vector search) | Not started | Week 8 |
| GCP Cloud Run | Not started | Week 10 |
| LoRA / QLoRA fine-tuning | Concept aware | Week 11 |
| GraphRAG / knowledge graphs | Not started | Week 12 |
| RLHF / DPO | Concept aware | Week 13 |

---

## Communication Style

| Preference | Detail |
|------------|--------|
| Format | Dense, structured. Uses Graphify for token efficiency. |
| Learning style | Video tutorials + hands-on building over reading docs |
| Feedback | Honest and direct — don't soften criticism |
| Code | Show working examples, explain WHY not just what |
| Context | Always connect to FinSight AI where possible |
| Antipatterns | Call them out proactively — production mindset |

---

## Project History

### Barclays — Wiglaf Risk Platform (most recent, most relevant)
- Risk analysis platform — 26 production versions
- Python/Flask, Celery, Redis, PostgreSQL
- Production CI/CD, monitoring, real financial risk calculations
- **Key strength:** production discipline, versioning, observability mindset
- **Interview differentiator:** real financial domain expertise

### Cognizant — ML Pipelines
- scikit-learn + PyCaret pipelines
- Data preprocessing, feature engineering, model evaluation
- **Key strength:** full ML lifecycle understanding

### FinSight AI (current — building now)
- Financial Risk Intelligence Platform on SEC EDGAR data
- Day 1: Hello World FastAPI, Dockerising
- Target: full multi-agent RAG system on GCP Cloud Run by Day 70

---

## What Not To Do

- Don't explain what Docker, FastAPI, Celery, Redis, or Pydantic is
- Don't explain basic Python syntax, decorators, or async patterns
- Don't explain what RAG, LangGraph, CrewAI are at a basic level after Week 2
- Don't suggest beginner courses for skills in the Expert list
- Don't pad responses — Kural uses Graphify, keep it dense
