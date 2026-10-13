---
title: RAG QA System
emoji: 🔍
colorFrom: indigo
colorTo: purple
sdk: gradio
app_file: space_app.py
pinned: false
license: mit
---

# RAG QA System

> Production-grade hybrid-retrieval RAG question-answering system with a real
> evaluation harness, cost tracking, and a streaming API.

This is a portfolio project that demonstrates the **most-deployed LLM pattern in
production** (RAG) done properly: not just a demo that runs, but one with
retrieval evals, a cross-encoder reranker, grounded citations, cost accounting,
and a CI-friendly eval gate.

---

## Problem statement

Naive RAG demos retrieve with a single bi-encoder, never measure retrieval
quality, and produce answers with no citations. They break on messy data,
ambiguous queries, and corpus drift. This project builds the version that
survives those conditions: **hybrid retrieval (BM25 + dense) fused with RRF,
cross-encoder reranking, grounded generation with inline citations, and a
golden-set eval that gates the build.**

---

## Architecture

```mermaid
flowchart LR
    D[("Documents<br/>.txt / .md")] --> C[Chunking<br/>sentence-boundary]
    C --> E[Embeddings<br/>all-MiniLM-L6-v2]
    E --> S[(Vector Store<br/>+ BM25 index)]

    Q[Question] --> R1["Hybrid Retrieval<br/>BM25 + dense → RRF fusion<br/>top-20"]
    S --> R1
    R1 --> R2["Cross-encoder Rerank<br/>ms-marco-MiniLM-L-6-v2<br/>top-5"]
    R2 --> G["Grounded Generation<br/>stub / OpenAI<br/>+ [n] citations"]
    G --> A[Answer + sources<br/>+ cost + latency]

    style C fill:#6C2BD9,color:#fff
    style R1 fill:#00A86B,color:#fff
    style R2 fill:#b8860b,color:#fff
    style G fill:#6C2BD9,color:#fff
```

**Two-stage retrieval** is the core design choice: a fast first stage (hybrid
BM25 + dense, fused via Reciprocal Rank Fusion) narrows ~20 candidates, then a
slower but more accurate cross-encoder re-scores query/passage pairs and keeps
the top 5. This trades a little latency for a large precision gain.

---

## Quick start

```bash
# 1. Clone & install (Python 3.10+)
git clone <your-fork-url> && cd rag-qa-system
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Copy config (defaults run fully offline — no API key needed)
cp .env.example .env

# 3. Run the evaluation harness (downloads ~80MB model on first run)
python -m eval.run_eval

# 4. Start the API
python -m app.main
# → http://localhost:8000/docs  (Swagger UI)
```

**Docker:**
```bash
docker compose up --build
```

### Ask a question

```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Reciprocal Rank Fusion?"}'
```

```json
{
  "answer": "Reciprocal Rank Fusion (RRF) combines rankings... [1]",
  "citations": [1],
  "sources": ["rag_architecture.md"],
  "latency_ms": 286.4,
  "cost_usd": 0.0015,
  "retrieved": [{"text": "...", "source": "rag_architecture.md", "rrf_score": 0.0333}]
}
```

---

## Evaluation results

Run on the 8-question golden set over the bundled sample corpus, with the
default `stub` LLM provider and `all-MiniLM-L6-v2` embeddings:

| Metric | Value | CI Gate | Status |
|---|---|---|---|
| **recall@5** | 1.00 | ≥ 0.80 | ✅ |
| **MRR** | 0.94 | ≥ 0.60 | ✅ |
| **faithfulness** | 0.98 | ≥ 0.60 | ✅ |
| **relevance** (lexical F1) | 0.23 | ≥ 0.20 | ✅ |
| **hallucination rate** | 0.00 | — | ✅ |
| p50 latency | 286 ms | — | — |
| p95 latency | 410 ms | — | — |
| cost / query | $0.0015 | — | — |

> **Why relevance looks low:** the `stub` LLM provider concatenates retrieved
> passages rather than rewriting them into natural prose, so lexical overlap
> with the natural-language "expected" answer is inherently limited. Switch
> `LLM_PROVIDER=openai` (set `OPENAI_API_KEY`) and relevance rises sharply
> while faithfulness stays high. The gate is calibrated for stub mode.

The eval script **exits non-zero if any gate is breached**, so it can gate a PR
in CI:

```bash
python -m eval.run_eval --json eval-report.json && echo "ship it" || echo "regression — do not ship"
```

---

## Cost analysis

Costs are tracked per query using configurable token prices (see `.env`).
With the stub provider, embedding cost dominates (local model = $0); with
OpenAI, generation dominates.

| Component | Model | Price (per 1M tokens) |
|---|---|---|
| Embeddings | all-MiniLM-L6-v2 (local) | $0.00 |
| Generation (stub) | local | $0.00 |
| Generation (OpenAI) | gpt-4o-mini | $0.15 in / $0.60 out |
| Reranker | ms-marco-MiniLM-L-6-v2 (local) | $0.00 |

At the observed ~1.5k tokens/query with gpt-4o-mini, generation cost is roughly
**$0.0003/query** — well under a cent. The eval reports `cost_per_query_usd`
so you can track drift as prompts or models change.

---

## Key design decisions & trade-offs

- **Hybrid retrieval over dense-only.** BM25 catches exact-term matches dense
  embeddings miss; dense catches semantic matches BM25 misses. RRF fuses them
  without needing score normalization. Cost: maintaining a second index.
- **Cross-encoder as a second stage, not first.** Cross-encoders are too slow
  to run over a full corpus. Retrieving 20 then reranking to 5 gets the
  precision benefit at acceptable latency (~300ms p50 on CPU).
- **In-memory vector store over a hosted DB.** Keeps the project runnable with
  zero infra. See "Production upgrade path" below for the swap.
- **Stub LLM provider by default.** Lets evals and tests run offline with no
  API key or cost. Real generation is one env var away.
- **Lexical metrics over LLM-as-judge.** recall@k, MRR, and overlap-based
  faithfulness need no API calls, so the CI gate is free to run on every PR.
  Trade-off: they are proxies, not NLI-grade. See "Next steps".

---

## Failure modes (honest)

These are where the system breaks or underperforms today:

1. **Cross-encoder cold start.** First query after startup loads the reranker
   (~1-2s). The eval harness warms up before timing; the API does not, so the
   first request is slower. Mitigation: pre-load on startup (TODO).
2. **Lexical faithfulness overcounts.** Token-overlap faithfulness flags common
   words as "supported" and misses semantic hallucinations (paraphrased
   invention). An LLM-as-judge would catch these.
3. **BM25 tokenizer is English-centric.** The `\w+` regex splits CJK text
   poorly. For Chinese corpora, swap in jieba tokenization.
4. **No incremental indexing.** Re-adding documents duplicates chunks. The
   store is rebuilt from scratch each run. Fine for a corpus of dozens;
   not for millions.
5. **Stub answers are not natural prose.** The stub concatenates passages, so
   answers read like a list, not a synthesized response. Only the `openai`
   provider produces natural answers.

---

## Production upgrade path

| This project | Production swap |
|---|---|
| In-memory numpy store | pgvector (<10M vectors) or Qdrant/Weaviate |
| `all-MiniLM-L6-v2` | `bge-large-en` or OpenAI `text-embedding-3-large` |
| Lexical overlap metrics | RAGAS / LLM-as-judge with human-validated rubric |
| Stub generator | OpenAI / Anthropic with prompt caching + model routing |
| Single-process FastAPI | vLLM + K8s with autoscaling + OpenTelemetry tracing |

The retrieval and pipeline interfaces are stable, so each swap is localized.

---

## Project structure

```
rag-qa-system/
├── app/
│   ├── main.py              # FastAPI app + startup indexing
│   ├── config.py            # pydantic-settings (env-driven)
│   ├── api/routes.py        # /ask, /ask/stream (SSE), /health, /stats
│   └── rag/
│       ├── chunking.py      # semantic sentence-boundary chunking
│       ├── embeddings.py    # sentence-transformers singleton
│       ├── store.py         # in-memory vector store + persistence
│       ├── retrieval.py     # BM25 + dense + RRF hybrid retrieval
│       ├── reranking.py     # cross-encoder second stage
│       ├── generation.py    # stub + OpenAI grounded generation
│       ├── cost.py          # token → USD accounting
│       └── pipeline.py      # end-to-end orchestrator
├── eval/
│   ├── golden_set.json      # 8 curated Q&A pairs
│   ├── metrics.py           # recall@k, MRR, faithfulness, relevance
│   └── run_eval.py          # CI-gated eval runner
├── data/sample_docs/        # 4 markdown docs as the corpus
├── tests/                   # pure-logic unit tests (no model downloads)
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## Tech stack

`Python 3.10+` · `FastAPI` · `sentence-transformers` · `rank-bm25` · `numpy` ·
`pydantic-settings` · `sse-starlette` · `Docker`

---

## License

MIT
