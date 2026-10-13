# Vector Databases

## Role in RAG

A vector database stores the embeddings of document chunks and supports fast
similarity search over them. It is the index that makes dense retrieval
possible at scale. The choice of vector database is one of the few
infrastructure decisions that is genuinely hard to reverse, so it matters.

## Choosing by scale

pgvector is fine for under 10 million vectors. It runs as a Postgres extension
so it fits naturally into stacks that already use Postgres, and it avoids
introducing a separate system to operate. For most workloads under that scale,
pgvector is the pragmatic default.

For larger corpora or specialized workloads, dedicated vector databases are
common choices. Pinecone is a managed service that became expensive at scale.
Weaviate, Qdrant, and Turbopuffer cover specialized cases such as hybrid
search, multi-tenancy, and high-throughput filtering.

## What to evaluate

When choosing a vector database, evaluate against load tests, not vendor blog
posts. The dimensions that matter are: recall at your target latency,
multi-tenancy isolation, filtering performance, cost at your vector count, and
operational burden. Hybrid search support (combining dense and lexical in one
query) is increasingly important.

## Embedding model versioning

The embedding model defines the vector space. If you change the embedding
model, every existing vector becomes invalid because it lives in a different
space. Strong teams version their embedding model and maintain a re-embed plan
so they can migrate the corpus when they upgrade.
