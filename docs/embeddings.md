# Embeddings (BGE)

## Model

- **Default:** `BAAI/bge-small-zh-v1.5` (512 dimensions)
- **Local path:** `models/bge-small-zh-v1.5/` (see `scripts/download_bge_model.py`)
- **Runtime:** `sentence-transformers` + **CPU PyTorch** (`torch==2.8.0+cpu` in `uv.lock`)

## Configuration

Environment variables (`EMBEDDINGS__*`):

| Variable | Default |
|----------|---------|
| `MODEL_NAME` | `BAAI/bge-small-zh-v1.5` |
| `MODEL_PATH` | `./models/bge-small-zh-v1.5` |
| `DEVICE` | `cpu` |
| `BATCH_SIZE` | `32` |
| `QUERY_INSTRUCTION` | `为这个句子生成表示以用于检索相关文章：` |

OpenSearch vector dimension must match: `OPENSEARCH__VECTOR_DIMENSION=512`

## Download model (host)

```bash
uv run python scripts/download_bge_model.py
```

Uses `HF_ENDPOINT` (default `https://hf-mirror.com` in Docker) for faster downloads in China.

## Docker build (API image)

The API image uses **Tsinghua PyPI** + **CPU-only PyTorch** (no ~3GB NVIDIA CUDA wheels):

```powershell
.\scripts\rebuild-api-docker.ps1
docker-compose up -d api
```

`compose.yml` mounts `./models:/app/models` and sets `EMBEDDINGS__MODEL_PATH=/app/models/bge-small-zh-v1.5`.

## Reindex after model change

When embedding dimension or model changes, rebuild OpenSearch chunks:

```bash
# Stack running; from host:
$env:OPENSEARCH__HOST = "http://localhost:9200"
uv run python scripts/reindex_opensearch.py --flush-redis
```

If `--flush-redis` fails on host (hostname `redis`), flush manually:

```bash
docker exec rag-redis redis-cli FLUSHDB
```

## Verify (Phase 6 checklist)

```bash
# Health + index
curl.exe http://localhost:8000/api/v1/health
curl.exe http://localhost:9200/arxiv-papers-chunks/_count

# Hybrid RAG
curl.exe -X POST http://localhost:8000/api/v1/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"什么是 transformer？\",\"top_k\":3,\"use_hybrid\":true}"

# Agentic RAG
curl.exe -X POST http://localhost:8000/api/v1/ask-agentic ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"attention mechanism 是什么？\",\"top_k\":3}"

# Unit tests
uv run pytest tests/unit -q
```

Inside the API container (BGE + torch already installed):

```bash
docker exec rag-api python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

## Migration note (Jina → BGE)

- Removed: `JINA_API_KEY`, remote Jina API client
- Index dimension: **1024 → 512** — must run `scripts/reindex_opensearch.py` once after switching
