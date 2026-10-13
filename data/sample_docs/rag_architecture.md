# RAG Architecture

## What is RAG

RAG stands for Retrieval-Augmented Generation. It is a pattern that combines a
retriever, which fetches relevant passages from a knowledge base, with a
generator, which conditions its answer on those passages. By grounding the
generator in retrieved source data, RAG reduces hallucination and lets the
system cite where its answers come from.

Long context windows did not kill RAG. They made naive RAG worse, because
engineers started stuffing hundreds of thousands of tokens of mediocre
retrieval into the prompt instead of fixing the retrieval. Strong RAG systems
still retrieve a small, high-precision context.

## Two-stage retrieval

A production RAG typically uses two retrieval stages. The first stage is a
fast bi-encoder (dense embeddings) plus lexical search (BM25), fused into a
single candidate list. The second stage is a cross-encoder reranker that
re-scores query-passage pairs for relevance.

A cross-encoder scores the query and passage together so they attend to each
other, giving better relevance estimates than a bi-encoder. It is slower than
a bi-encoder, so it is used as a second stage after fast first-stage
retrieval narrows the candidates.

## Reciprocal Rank Fusion

Reciprocal Rank Fusion (RRF) combines rankings from multiple retrievers using
the formula score = sum of 1/(k + rank) for each retriever. The constant k is
usually 60. RRF needs no score normalization, which makes it robust for fusing
BM25 scores and dense cosine scores that live on entirely different scales.
This is the standard hybrid-retrieval recipe.

## Hybrid search

Hybrid search means combining lexical (BM25) and semantic (dense) retrieval.
BM25 is strong for keyword and exact-term matches; dense retrieval is strong
for semantic similarity even when no words overlap. Fusing them with RRF
covers both failure modes and is what most production RAG systems do.
