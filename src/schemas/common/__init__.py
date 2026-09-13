'''
统一管理所有数据模型，简化导入路径，规范项目结构，方便维护和查找
方便别的地方导入，只需要一行from src.schemas import就能导入不同文件里面的类或者函数
'''
from src.schemas.api.health import HealthResponse, ServiceStatus
from src.schemas.api.search import SearchHit, SearchRequest, SearchResponse

from src.schemas.arxiv.paper import (
    ArxivPaper,
    PaperBase,
    PaperCreate,
    PaperResponse,
    PaperSearchResponse,
)

from src.schemas.database.config import PostgreSQLSettings

from src.schemas.indexing.models import ChunkMetadata, TextChunk

from src.schemas.pdf_parser.models import (
    ArxivMetadata,
    PaperFigure,
    PaperSection,
    PaperTable,
    ParsedPaper,
    ParserType,
    PdfContent,
)

from src.schemas.api.search import HybridSearchRequest

__all__ = [
    # API 接口
    "HealthResponse",
    "ServiceStatus",
    "SearchRequest",
    "SearchResponse",
    "SearchHit",
    # arXiv 论文
    "ArxivPaper",
    "PaperBase",
    "PaperCreate",
    "PaperResponse",
    "PaperSearchResponse",
    # 索引分块
    "ChunkMetadata",
    "TextChunk",
    # 数据库
    "PostgreSQLSettings",
    # PDF 解析
    "ParserType",
    "PaperSection",
    "PaperFigure",
    "PaperTable",
    "PdfContent",
    "ArxivMetadata",
    "ParsedPaper",
    # 检索
    "HybridSearchRequest",
]
