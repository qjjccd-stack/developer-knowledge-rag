# Chunking Strategies

## Why chunking matters

Chunking is how a long document is split into smaller pieces that can be
embedded and retrieved individually. The chunking strategy directly affects
retrieval quality: chunks that are too large dilute relevance, chunks that are
too small fragment the context needed to answer a question.

## Character-count vs semantic chunking

Character-count chunking cuts text at fixed intervals, for example every 512
characters. It is simple but can split a sentence or a clause in the middle,
destroying the meaning of that chunk and hurting both embedding quality and
generation.

Semantic chunking splits on sentence or paragraph boundaries first, then
merges adjacent sentences up to a target size. This preserves meaning within
each chunk because sentences stay intact. Semantic chunking is the
recommended default for production RAG.

## Chunk size trade-offs

Smaller chunks improve retrieval precision because each chunk is more focused
on a single idea, so the embedding better represents that idea. The trade-off
is that small chunks may fragment the context needed to answer synthesis
questions that span multiple sentences.

Larger chunks preserve more context but dilute relevance: a chunk covering
many topics matches many queries weakly rather than one query strongly. There
is no universal best size; it should be tuned against a retrieval eval set.

## Overlap

Overlap means the tail of one chunk is repeated at the start of the next.
Overlap helps preserve continuity across chunk boundaries so that an idea
spanning a boundary is not lost. A typical overlap is 10-15 percent of the
chunk size. Overlap increases storage and embedding cost, so it is a
precision-vs-cost trade-off.
