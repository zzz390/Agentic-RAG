"""
为 BGE 向量重建 OpenSearch chunk 索引，并从 PostgreSQL 重新索引全部论文。

若从旧版远程嵌入（1024 维）切换到 BGE（512 维）后典型用法：

    uv run python scripts/reindex_opensearch.py
    uv run python scripts/reindex_opensearch.py --flush-redis
    uv run python scripts/reindex_opensearch.py --skip-recreate   # 保留已有 512 维索引
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

# 支持在项目根目录执行：uv run python scripts/reindex_opensearch.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import get_settings
from src.db.factory import make_database
from src.models.paper import Paper
from src.repositories.paper import PaperRepository
from src.services.cache.factory import make_redis_client
from src.services.embeddings.factory import make_embeddings_client
from src.services.indexing.factory import make_hybrid_indexing_service
from src.services.opensearch.factory import make_opensearch_client_fresh

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("reindex_opensearch")


def paper_to_dict(paper: Paper) -> Dict[str, Any]:
    return {
        "id": str(paper.id),
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "categories": paper.categories,
        "published_date": paper.published_date,
        "raw_text": paper.raw_text,
        "sections": paper.sections,
    }


def load_papers_with_raw_text(batch_size: int = 50) -> List[Dict[str, Any]]:
    database = make_database()
    papers_data: List[Dict[str, Any]] = []
    offset = 0

    with database.get_session() as session:
        repo = PaperRepository(session)
        while True:
            batch = repo.get_papers_with_raw_text(limit=batch_size, offset=offset)
            if not batch:
                break
            papers_data.extend(paper_to_dict(paper) for paper in batch)
            offset += batch_size

    return papers_data


def verify_index(opensearch_client, expected_dimension: int) -> Dict[str, Any]:
    index_name = opensearch_client.index_name
    dimension = opensearch_client.get_index_embedding_dimension()
    count_response = opensearch_client.client.count(index=index_name)
    total_chunks = count_response.get("count", 0)

    paper_count_response = opensearch_client.client.search(
        index=index_name,
        body={"size": 0, "aggs": {"unique_papers": {"cardinality": {"field": "arxiv_id"}}}},
    )
    unique_papers = paper_count_response["aggregations"]["unique_papers"]["value"]

    if dimension != expected_dimension:
        raise RuntimeError(
            f"Index embedding dimension is {dimension}, expected {expected_dimension}. "
            "Re-run with default options to recreate the index."
        )

    return {
        "index_name": index_name,
        "embedding_dimension": dimension,
        "total_chunks": total_chunks,
        "unique_papers": unique_papers,
    }


def flush_redis_cache() -> None:
    settings = get_settings()
    try:
        redis_client = make_redis_client(settings)
        redis_client.flushdb()
        logger.info("Redis cache flushed (DB %s)", settings.redis.db)
    except Exception as e:
        logger.warning("Could not flush Redis cache: %s", e)


async def run_reindex(*, recreate_index: bool, flush_redis: bool, paper_batch_size: int) -> Dict[str, Any]:
    settings = get_settings()
    expected_dimension = settings.opensearch.vector_dimension

    embeddings_client = make_embeddings_client(settings)
    model_dimension = embeddings_client.vector_dimension
    if model_dimension != expected_dimension:
        raise RuntimeError(
            f"BGE model dimension ({model_dimension}) != OPENSEARCH__VECTOR_DIMENSION ({expected_dimension})"
        )

    opensearch_client = make_opensearch_client_fresh(settings)
    if not opensearch_client.health_check():
        raise RuntimeError(
            f"OpenSearch is not reachable at {settings.opensearch.host}. "
            "Start Docker Compose or set OPENSEARCH__HOST."
        )

    existing_dimension = opensearch_client.get_index_embedding_dimension()
    if existing_dimension is not None and existing_dimension != expected_dimension:
        logger.warning(
            "Existing index dimension=%s does not match configured %s; recreating index.",
            existing_dimension,
            expected_dimension,
        )
        recreate_index = True

    if recreate_index:
        logger.info("Recreating hybrid index and RRF pipeline (force=True)...")
        opensearch_client.setup_indices(force=True)
    else:
        opensearch_client.setup_indices(force=False)

    papers = load_papers_with_raw_text(batch_size=paper_batch_size)
    if not papers:
        logger.warning(
            "No papers with raw_text found in PostgreSQL. "
            "Run the arXiv ingestion pipeline first, then re-run this script."
        )
        return {"papers_indexed": 0, "total_chunks_indexed": 0, "verification": verify_index(opensearch_client, expected_dimension)}

    logger.info("Reindexing %s papers with BGE (%s)...", len(papers), embeddings_client.model_name)
    indexing_service = make_hybrid_indexing_service(settings)
    stats = await indexing_service.index_papers_batch(papers=papers, replace_existing=True)

    verification = verify_index(opensearch_client, expected_dimension)
    logger.info(
        "Reindex complete: %s papers, %s chunks indexed, index=%s, dimension=%s",
        stats["papers_processed"],
        stats["total_chunks_indexed"],
        verification["index_name"],
        verification["embedding_dimension"],
    )

    if flush_redis:
        flush_redis_cache()

    return {**stats, "verification": verification}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="重建 OpenSearch 分块索引并使用 BGE 重新入库。")
    parser.add_argument(
        "--skip-recreate",
        action="store_true",
        help="Do not delete/recreate the chunk index (only safe if dimension already matches).",
    )
    parser.add_argument(
        "--flush-redis",
        action="store_true",
        help="Flush Redis after reindex to drop stale /ask cache entries.",
    )
    parser.add_argument(
        "--paper-batch-size",
        type=int,
        default=50,
        help="PostgreSQL pagination size when loading papers.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = asyncio.run(
            run_reindex(
                recreate_index=not args.skip_recreate,
                flush_redis=args.flush_redis,
                paper_batch_size=args.paper_batch_size,
            )
        )
        print(result)
        return 0
    except Exception as e:
        logger.error("Reindex failed: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
