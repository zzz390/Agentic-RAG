import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

# 导入缓存好的服务工具
from .common import get_cached_services

logger = logging.getLogger(__name__)

#根据指定日期，从 arXiv 抓取论文、解析 PDF 并存入数据库。
async def run_paper_ingestion_pipeline(
    target_date: str,
    process_pdfs: bool = True,
) -> dict:
    """
    论文入库流程的异步封装函数。

    :param target_date: 要抓取论文的日期（格式 YYYYMMDD）
    :param process_pdfs: 是否下载并处理 PDF
    :returns: 包含入库统计信息的字典
    """
    # 获取初始化好的核心服务（只拿需要用的）
    arxiv_client, _, database, metadata_fetcher, _ = get_cached_services()

    # 从配置中获取最大论文抓取数量
    max_results = arxiv_client.max_results
    logger.info(f"Using default max_results from config: {max_results}")

    # 获取数据库会话
    with database.get_session() as session:
        # 调用抓取服务，处理并存储论文
        return await metadata_fetcher.fetch_and_process_papers(
            max_results=max_results,
            from_date=target_date,
            to_date=target_date,
            process_pdfs=process_pdfs,
            store_to_db=True,
            db_session=session,
        )

#定时任务入口：自动计算昨天日期，调用上面的抓取流程，把论文自动入库并记录结果。
def fetch_daily_papers(**context):
    """
    从 arXiv 抓取每日论文并存入 PostgreSQL 数据库。

    该任务流程：
    1. 确定目标日期（默认为昨天）
    2. 从 arXiv API 获取论文
    3. 使用 Docling 下载并解析 PDF
    4. 将元数据和解析内容存入 PostgreSQL

    注意：OpenSearch 索引由单独的专门任务处理
    """
    logger.info("Starting daily paper fetching task")

    # 从 Airflow 上下文获取执行时间
    execution_date = context.get("execution_date")
    if execution_date:
        # 如果有执行日期，目标日期为前一天
        target_dt = execution_date - timedelta(days=1)
        target_date = target_dt.strftime("%Y%m%d")
    else:
        # 否则默认使用昨天
        yesterday = datetime.now() - timedelta(days=1)
        target_date = yesterday.strftime("%Y%m%d")

    logger.info(f"Fetching papers for date: {target_date}")

    # 同步调用异步的论文处理流程
    results = asyncio.run(
        run_paper_ingestion_pipeline(
            target_date=target_date,
            process_pdfs=True,
        )
    )

    logger.info(f"Daily fetch complete: {results['papers_fetched']} papers for {target_date}")

    # 把日期加入结果
    results["date"] = target_date
    # 推送到 Airflow XCom（任务间通信）
    ti = context.get("ti")
    if ti:
        ti.xcom_push(key="fetch_results", value=results)

    return results