# Local embedding models

Weights are **not** committed to Git (see `.gitignore`).

## BGE-small-zh-v1.5

- Hugging Face: `BAAI/bge-small-zh-v1.5`
- Vector dimension: **512**
- Local path: `models/bge-small-zh-v1.5/`

Download (uses hf-mirror by default):

```bash
uv run python scripts/download_bge_model.py
```

Docker Compose mounts `./models` into the API container at `/app/models`.

## After switching embedding models

OpenSearch chunk index must be recreated when vector dimension changes:

```bash
uv run python scripts/reindex_opensearch.py --flush-redis
```

Requires PostgreSQL (papers with `raw_text`) and OpenSearch to be running.

See [docs/embeddings.md](../docs/embeddings.md) for Docker build and verification steps.
