# 混合检索与重排评测

评测日期：2026-09-02
报告文件：[retrieval-hybrid-evaluation.json](../../agent-service/reports/retrieval-hybrid-evaluation.json)

## 目标

验证 Dense、Dense + BM25 + RRF、Dense + BM25 + RRF + Cross-Encoder 三条链路，重点观察：

- 正向知识问题是否命中 Top-3；
- 相关资料是否尽量排在前面（MRR@3、nDCG@3）；
- 未知租户是否返回空结果；
- 候选集扩大和重排带来的延迟成本。

## 实验设置

- 评测集：30 条案例，其中 27 条有明确知识来源，3 条使用不存在知识的租户验证隔离；
- 数据：`company_001` 的退款/物流文档与 `evaluation_001` 的评测文档，共 3 个文档、13 个 chunk；
- Dense：`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，Cosine；
- Sparse：Qdrant 的 `Qdrant/bm25`，开启 IDF；
- 融合：Qdrant `RetrievalMode.HYBRID` 的 RRF；
- 重排：本地 CPU `BAAI/bge-reranker-base` Cross-Encoder；
- 最终返回 `top_k=3`，混合链路先取 `candidate_k=10`；每个案例重复 3 次，P95 排除了首次模型加载。

## 结果

| 链路 | 正向 Hit@3 | 正向 MRR@3 | 正向 nDCG@3 | 总通过率 | P95 延迟 | 租户泄漏 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dense | 96.2963% | 0.8704 | 0.8937 | 29/30 | 71.802 ms | 0 |
| Dense + BM25 + RRF | 96.2963% | 0.8704 | 0.8937 | 29/30 | 23.162 ms | 0 |
| Dense + BM25 + RRF + Cross-Encoder | 100% | 1.0000 | 1.0000 | 30/30 | 370.387 ms | 0 |

相对 Dense 基线，最终链路的 MRR@3 提升 `0.1296`，nDCG@3 提升 `0.1063`，Hit@3 提升 `3.7037` 个百分点。3 条未知租户案例全部返回空结果，跨租户泄漏为 0。

## 如何解读

本数据集较小，单独加入 BM25/RRF 后总体排名与 Dense 相同；真正把弱案例从 Top-3 边界拉回来的，是“先召回 10 个候选，再用 Cross-Encoder 重排”。因此简历应写成完整链路带来的提升，不应声称 BM25 单独提升了指标。

重排使用 CPU，P95 从 71.802 ms 增加到 370.387 ms，这是准确性与延迟的明确权衡。生产环境可按问题类型、候选数量和硬件重新压测，不能把本地 P95 直接当成线上 SLO。

## 可复现实验

```powershell
cd agent-service
$env:UV_CACHE_DIR='D:\Documents\agent\.uv-cache'
$env:PYTHONPATH='src'
uv run python scripts/evaluate_retrieval.py `
  --reindex `
  --repetitions 3 `
  --output reports/retrieval-hybrid-evaluation.json
```

核心实现位置：

- `src/agent_service/rag/vector_store.py`：命名 Dense/BM25 向量、IDF 和 Hybrid Store；
- `src/agent_service/rag/retrieval.py`：租户 Filter、候选召回和重排；
- `src/agent_service/rag/reranking.py`：Cross-Encoder 的异步线程封装；
- `scripts/evaluate_retrieval.py`：三条链路的同口径对照评测。
