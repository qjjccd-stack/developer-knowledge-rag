# Evaluating RAG Systems

## Why evaluate

If you cannot measure your RAG system, you cannot ship it. Models change,
prompts drift, and data changes. The only way to know the system still works
is to re-run an evaluation set on every change. Teams that ship without
evals ship by vibe, and vibe-shipped systems regress in production.

## Retrieval metrics

Retrieval metrics are evaluated on the retriever alone, before any generation.
The most common is recall@k, which measures the fraction of relevant items
that appear in the top-k retrieved results. recall@k is the single most
important retrieval metric because if the relevant passage is not retrieved,
no generator can rescue the answer.

Mean Reciprocal Rank (MRR) measures the rank position of the first relevant
result, rewarding systems that surface the right passage early. Precision@k
measures how many of the top-k are relevant, which matters when the generator
reads all of them.

## Generation metrics

Faithfulness measures whether the answer is supported by the retrieved
context. A hallucination is content in the generated answer that is not
supported by the retrieved context. Faithfulness is the fraction of answer
claims or tokens that are grounded in the context. Low faithfulness means the
model is inventing content.

Answer relevance measures whether the answer actually addresses the question
asked, as opposed to being grounded but off-topic. A good answer is both
faithful and relevant.

## LLM-as-judge

Overlap-based metrics are cheap proxies. For sharper evaluation, use an
LLM-as-judge: a stronger model scores the answer on a rubric covering
faithfulness, relevance, and completeness. LLM-as-judge should be validated
against human spot-checks to confirm agreement before it is trusted as a gate.
