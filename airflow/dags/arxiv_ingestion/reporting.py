import json
import logging
from datetime import datetime

# 导入缓存服务
from .common import get_cached_services

logger = logging.getLogger(__name__)

#收集当天论文抓取、索引构建的所有统计数据，
# 生成一份完整的每日运行报告，包含论文数量、分块数、数据库总量、索引状态。
def generate_daily_report(**context):
    """
    生成数据入库流程的每日统计报告。

    收集前面所有任务的统计数据，生成一份汇总报告。
    """
    logger.info("Generating daily ingestion report")

    # 获取任务实例（Airflow 上下文）
    ti = context.get("ti")
    if not ti:
        logger.warning("No task instance available, generating basic report")
        return {"status": "basic_report", "message": "No task instance for XCom data"}

    # 从上游任务拉取统计结果
    fetch_stats = ti.xcom_pull(task_ids="fetch_daily_papers", key="fetch_results") or {}
    hybrid_stats = ti.xcom_pull(task_ids="index_papers_hybrid", key="hybrid_index_stats") or {}

    # 组装报告主体
    report = {
        "execution_date": context.get("execution_date", datetime.now()).isoformat(),
        "fetch_statistics": {
            "papers_fetched": fetch_stats.get("papers_fetched", 0),
            "papers_stored": fetch_stats.get("papers_stored", 0),
            "target_date": fetch_stats.get("date", "unknown"),
        },
        "indexing_statistics": {
            "papers_processed": hybrid_stats.get("papers_processed", 0),
            "chunks_created": hybrid_stats.get("total_chunks_created", 0),
            "chunks_indexed": hybrid_stats.get("total_chunks_indexed", 0),
            "embeddings_generated": hybrid_stats.get("total_embeddings_generated", 0),
        },
        "pipeline_status": "success" if fetch_stats and hybrid_stats else "partial",
    }

    try:
        # 获取服务实例
        _arxiv_client, _pdf_parser, database, _metadata_fetcher, opensearch_client = get_cached_services()

        # 查询数据库总论文数
        with database.get_session() as session:
            from sqlalchemy import func
            from src.models.paper import Paper

            total_papers = session.query(func.count(Paper.id)).scalar()
            report["database_statistics"] = {"total_papers": total_papers}

        # 检查 OpenSearch 状态并获取索引统计
        if opensearch_client.health_check():
            try:
                stats_response = opensearch_client.client.indices.stats(index=opensearch_client.index_name)
                count_response = opensearch_client.client.count(index=opensearch_client.index_name)
                index_stats = stats_response["indices"][opensearch_client.index_name]["total"]

                report["opensearch_statistics"] = {
                    "index_name": opensearch_client.index_name,
                    "document_count": count_response["count"],
                    "index_size_mb": round(index_stats["store"]["size_in_bytes"] / (1024 * 1024), 2),
                }
            except Exception as stats_error:
                logger.error(f"Failed to get OpenSearch statistics: {stats_error}")
                report["opensearch_statistics"] = {"index_name": opensearch_client.index_name, "error": str(stats_error)}
    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        report["error"] = str(e)

    # 打印并推送报告
    logger.info("Daily Ingestion Report:")
    logger.info(json.dumps(report, indent=2))

    ti.xcom_push(key="daily_report", value=report)

    return report