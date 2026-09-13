import logging
import sys
from functools import lru_cache
from typing import Any, Tuple

# 将 /opt/airflow 加入系统路径
sys.path.insert(0, "/opt/airflow")

# 导入各个服务的工厂创建函数
from src.db.factory import make_database
from src.services.arxiv.factory import make_arxiv_client
from src.services.metadata_fetcher import make_metadata_fetcher
from src.services.opensearch.factory import make_opensearch_client
from src.services.pdf_parser.factory import make_pdf_parser_service

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)

#统一创建所有核心服务并只缓存一份，供整个系统重复使用，不重复初始化。
# 缓存装饰器：最多缓存 1 份结果，确保全局只初始化一次
@lru_cache(maxsize=1)
def get_cached_services() -> Tuple[Any, Any, Any, Any, Any]:
    """
    使用 lru_cache 缓存服务实例，实现自动缓存。

    返回：
        服务元组 (arxiv客户端, PDF解析器, 数据库, 元数据抓取器, opensearch客户端)
    """
    logger.info("Initializing services (cached with lru_cache)")

    # 初始化核心服务
    arxiv_client = make_arxiv_client()
    pdf_parser = make_pdf_parser_service()
    database = make_database()
    opensearch_client = make_opensearch_client()

    # 初始化元数据抓取服务（依赖前两个服务）
    metadata_fetcher = make_metadata_fetcher(arxiv_client, pdf_parser)

    logger.info("All services initialized and cached with lru_cache")
    return arxiv_client, pdf_parser, database, metadata_fetcher, opensearch_client