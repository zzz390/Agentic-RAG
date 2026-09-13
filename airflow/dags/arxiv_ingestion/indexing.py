import asyncio
import logging
from datetime import datetime, timedelta, timezone

from src.db.factory import make_database
from src.services.indexing.factory import make_hybrid_indexing_service
from src.services.opensearch.factory import make_opensearch_client_fresh

logger = logging.getLogger(__name__)

#论文转成字典格式，分块 + 生成向量 + 批量写入 OpenSearch。
async def _index_papers_with_chunks(papers):
    """异步辅助函数：对论文进行分块、生成向量并建立索引"""
    indexing_service = make_hybrid_indexing_service()

    papers_data = []
    for paper in papers:
        if hasattr(paper, "__dict__"):
            paper_dict = {
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
        else:
            paper_dict = paper
        papers_data.append(paper_dict)

    stats = await indexing_service.index_papers_batch(papers=papers_data, replace_existing=True)

    return stats

#从数据库读取最近的论文，自动分块、生成向量、建立混合检索索引，供 RAG 系统搜索使用。
def index_papers_hybrid(**context):
    """
    对论文进行分块与向量嵌入索引，用于混合检索。

    任务流程：
    1. 从 PostgreSQL 读取最近处理好的论文
    2. 将论文分块（600词，重叠100词）
    3. 使用本地 BGE 生成向量嵌入
    4. 将分块与向量存入 OpenSearch 建立索引
    """
    try:
        database = make_database()

        ti = context.get("ti")

        fetch_results = None
        if ti:
            fetch_results = ti.xcom_pull(task_ids="fetch_daily_papers", key="fetch_results")

        with database.get_session() as session:
            from src.models.paper import Paper

            if fetch_results and fetch_results.get("papers_stored", 0) > 0:
                from sqlalchemy import desc

                papers = session.query(Paper).order_by(desc(Paper.created_at)).limit(fetch_results["papers_stored"]).all()
            else:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=1)
                papers = session.query(Paper).filter(Paper.created_at >= cutoff_date).all()

            if not papers:
                logger.info("No papers to index for hybrid search")
                return {"papers_indexed": 0, "chunks_created": 0}

            logger.info(f"Indexing {len(papers)} papers for hybrid search")

            stats = asyncio.run(_index_papers_with_chunks(papers))

            logger.info(
                f"Hybrid indexing complete: {stats['papers_processed']} papers, "
                f"{stats['total_chunks_created']} chunks created, "
                f"{stats['total_chunks_indexed']} chunks indexed"
            )

            if ti:
                ti.xcom_push(key="hybrid_index_stats", value=stats)

            return stats

    except Exception as e:
        logger.error(f"Failed to index papers for hybrid search: {e}")
        raise

#检查 OpenSearch 索引是否健康，统计总分块数、论文数、索引大小，用于监控和日志。
def verify_hybrid_index(**context):
    """检查混合索引状态是否健康，并获取统计信息"""
    try:
        opensearch_client = make_opensearch_client_fresh()

        stats = opensearch_client.client.indices.stats(index=opensearch_client.index_name)

        count = opensearch_client.client.count(index=opensearch_client.index_name)

        paper_count_query = {"aggs": {"unique_papers": {"cardinality": {"field": "arxiv_id"}}}, "size": 0}

        paper_count_response = opensearch_client.client.search(index=opensearch_client.index_name, body=paper_count_query)

        unique_papers = paper_count_response["aggregations"]["unique_papers"]["value"]

        result = {
            "index_name": opensearch_client.index_name,
            "total_chunks": count["count"],
            "unique_papers": unique_papers,
            "avg_chunks_per_paper": (count["count"] / unique_papers if unique_papers > 0 else 0),
            "index_size_mb": stats["indices"][opensearch_client.index_name]["total"]["store"]["size_in_bytes"] / (1024 * 1024),
        }

        logger.info(
            f"Hybrid index stats: {result['total_chunks']} chunks, "
            f"{result['unique_papers']} papers, "
            f"{result['avg_chunks_per_paper']:.1f} chunks/paper"
        )

        return result

    except Exception as e:
        logger.error(f"Failed to verify hybrid index: {e}")
        raise