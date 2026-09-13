from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UploadParserType(str, Enum):
    DOCLING = "docling"
    TXT = "txt"
    MARKDOWN = "markdown"
    DOCX = "docx"
    EXCEL = "excel"


class ParsedUploadDocument(BaseModel):
    raw_text: str = Field(..., description="提取的全文纯文本")
    sections: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="可选章节列表（含 title/content 等键）",
    )
    parser_used: UploadParserType = Field(..., description="产生内容的解析器")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="解析器附加元数据")
    original_filename: str = Field(..., description="原始上传文件名")
    file_extension: str = Field(..., description="规范化小写扩展名，如 .pdf")
    title_hint: str = Field(..., description="由文件名或文档属性推断的标题")


class UploadIngestStatus(str, Enum):
    INDEXED = "indexed"
    PARTIAL = "partial"
    FAILED = "failed"


class UploadIngestResult(BaseModel):
    document_id: UUID
    arxiv_id: str
    title: str
    original_filename: str
    chunks_created: int
    chunks_indexed: int
    embeddings_generated: int
    parser_used: str
    status: UploadIngestStatus
    message: Optional[str] = None
