from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PaperSummary(BaseModel):
    id: UUID
    arxiv_id: str = Field(..., description="文档标识（arXiv ID 或 upload-{uuid}）")
    title: str
    authors: List[str]
    abstract: str
    categories: List[str]
    source_type: str = Field(..., description="来源：arxiv 或 upload")
    pdf_url: str
    pdf_processed: bool
    has_full_text: bool = Field(..., description="是否包含 raw_text 全文")
    published_date: datetime

    class Config:
        from_attributes = True


class PaperFullResponse(PaperSummary):
    raw_text: Optional[str] = Field(None, description="提取的全文（include_full_text=true 时返回）")
    sections: Optional[List[Dict[str, Any]]] = Field(None, description="结构化章节（若有）")
    references: Optional[List[Dict[str, Any]]] = None
    parser_used: Optional[str] = None
    parser_metadata: Optional[Dict[str, Any]] = None
    pdf_processing_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PaperListResponse(BaseModel):
    papers: List[PaperSummary]
    total: int
    limit: int
    offset: int
