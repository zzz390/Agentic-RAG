## BGE client

- `BGEEmbeddingsClient`：本地 `sentence-transformers` 加载 `BAAI/bge-small-zh-v1.5`（512 维）。
- `embed_passages`：批量将 chunk 文本向量化，供 OpenSearch 入库。
- `embed_query`：用户问题向量化（带 BGE 检索用 query 前缀）。
- 配置见 `EmbeddingsSettings`（`EMBEDDINGS__*` 环境变量）。

## Factory

- `make_embeddings_service` / `make_embeddings_client`：从配置创建 `BGEEmbeddingsClient`。
