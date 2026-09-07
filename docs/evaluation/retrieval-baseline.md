# Retrieval evaluation baseline (historical)

Date: 2026-08-28

This is the six-case Dense-only learning baseline. The current 30-case
Dense/BM25/RRF/Cross-Encoder comparison is documented in
`retrieval-hybrid-rerank.md`.

## Configuration

- Embedding: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Vector database: Qdrant
- Distance: cosine
- `top_k`: 3
- Positive cases: 5
- Expected-empty cases: 1

The evaluation uses local Embedding inference and Qdrant retrieval only. It does
not start FastAPI or Java and does not call an external LLM.

## Summary

| Metric | Result |
| --- | ---: |
| Total cases | 6 |
| Pass rate | 100% |
| Hit@3 | 100% |
| MRR@3 | 0.8667 |
| Empty-result accuracy | 100% |
| Tenant-isolation violations | 0 |

## Positive-case ranking

| Case | Expected section | First relevant rank | Score |
| --- | --- | ---: | ---: |
| `refund-unshipped-cancel` | 未发货订单 | 1 | 0.7266 |
| `refund-opened-software` | 七天无理由退货 | 3 | 0.4626 |
| `refund-quality-shipping-fee` | 质量问题 | 1 | 0.5193 |
| `shipping-live-location` | 物流轨迹 | 1 | 0.5707 |
| `shipping-delay` | 物流延迟 | 1 | 0.6153 |

## Findings

- All expected sources appear in the top three results.
- Four of five positive cases rank the expected source first.
- `refund-opened-software` is the weak case: the expected section appears only
  at rank 3. It currently passes Hit@3 but can fall out of the context when the
  knowledge base grows.
- A full-candidate diagnostic confirms that the first two results are
  `退款资格说明` (0.5612) and `未发货订单` (0.4873), ahead of the expected
  `七天无理由退货` section (0.4626).
- The original query uses `无理由退款`, while the expected policy primarily
  uses `七天无理由退货`. With the current small multilingual embedding model,
  repeated broad refund wording outweighs the more decisive constraints
  `拆封` and `软件`. This is a ranking-quality weakness, not missing indexing,
  tenant-filter failure, or a Qdrant availability problem.
- The unknown-tenant case returns no documents, and no returned chunk violates
  the requested tenant boundary.
- Similarity scores are recorded for comparison, not treated as stable business
  confidence or hard-coded pass thresholds.

## Next decision

The controlled dual-query experiment kept the original question and added
`已经拆封的软件是否支持七天无理由退货？` as a normalized query:

| Retrieval path | Expected-section rank |
| --- | ---: |
| Original query | 3 |
| Rewritten query | 1 |
| Equal-weight RRF fusion | 2 |

The experiment confirms the terminology mismatch and improves the fused rank,
but it does not put the expected section first: `退款资格说明` ranks 1 and 2 in
the two searches, while the expected section ranks 3 and 1. One manually
rewritten case is not sufficient evidence for adding an online query-rewriting
dependency, latency, and failure mode. Production retrieval therefore remains
unchanged. Revisit query rewriting, hybrid retrieval, or reranking after the
evaluation set grows and a repeatable before/after gain is demonstrated.
