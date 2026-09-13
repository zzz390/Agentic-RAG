from functools import lru_cache
from typing import Optional

from src.config import Settings, get_settings

from .client import OpenSearchClient

#创建并返回一个Opensearch，并且全局只创建一个，全局复用一个链接。
@lru_cache(maxsize=1)
def make_opensearch_client(settings: Optional[Settings] = None) -> OpenSearchClient:#Optional[Settings]等价于Union[Settings, None]，即这个值即可以是Settings也可以为空
    if settings is None:
        settings = get_settings()

    return OpenSearchClient(host=settings.opensearch.host, settings=settings)

#每次调用都创建一个全新的客户端，不缓存，测试、需要临时链接不同Opensearch地址的时候使用
def make_opensearch_client_fresh(settings: Optional[Settings] = None, host: Optional[str] = None) -> OpenSearchClient:
    if settings is None:
        settings = get_settings()

    opensearch_host = host or settings.opensearch.host

    return OpenSearchClient(host=opensearch_host, settings=settings)
