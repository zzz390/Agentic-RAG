from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

class ArxivPaper(BaseModel):
#和前的数据库的paper不一样，那个paper主要是存到数据库给数据库用的
#这个paper主要是用来给接口、数据传输用的

    arxiv_id: str = Field(..., description="arXiv 论文 ID")
    title: str = Field(..., description="论文标题")
    authors: List[str] = Field(..., description="作者列表")
    abstract: str = Field(..., description="摘要")
    categories: List[str] = Field(..., description="分类")
    published_date: str = Field(..., description="arXiv 发表日期（ISO 格式）")
    pdf_url: str = Field(..., description="PDF 下载地址")


class PaperBase(BaseModel):
#公共基础模板，别的类可以直接继承他
#ArxivPaper是刚从 arXiv 爬下来的原始数据，date是str类型
#PaperBase是处理干净、准备存数据库的标准数据，date是datetime类型

    arxiv_id: str = Field(..., description="arXiv 论文 ID")
    title: str = Field(..., description="论文标题")
    authors: List[str] = Field(..., description="作者列表")
    abstract: str = Field(..., description="摘要")
    categories: List[str] = Field(..., description="分类")
    published_date: datetime = Field(..., description="arXiv 发表日期")
    pdf_url: str = Field(..., description="PDF 下载地址")


class PaperCreate(PaperBase):
#存进数据库用的格式

    #获取全文其他内容
    raw_text: Optional[str] = Field(None, description="从 PDF 提取的全文")
    sections: Optional[List[Dict[str, Any]]] = Field(None, description="章节列表（标题与内容）")
    references: Optional[List[Dict[str, Any]]] = Field(None, description="参考文献列表（若已提取）")

    #解析器
    parser_used: Optional[str] = Field(None, description="使用的解析器（如 DOCLING）")
    parser_metadata: Optional[Dict[str, Any]] = Field(None, description="解析器附加元数据")
    pdf_processed: Optional[bool] = Field(False, description="PDF 是否已成功处理")
    pdf_processing_date: Optional[datetime] = Field(None, description="PDF 处理时间")


class PaperResponse(PaperBase):
#从数据库查出来之后，最终展示给外界的数据
    id: UUID

    raw_text: Optional[str] = Field(None, description="从 PDF 提取的全文")
    sections: Optional[List[Dict[str, Any]]] = Field(None, description="章节列表（标题与内容）")
    references: Optional[List[Dict[str, Any]]] = Field(None, description="参考文献列表（若已提取）")

    parser_used: Optional[str] = Field(None, description="使用的解析器")
    parser_metadata: Optional[Dict[str, Any]] = Field(None, description="解析器附加元数据")
    pdf_processed: bool = Field(False, description="PDF 是否已成功处理")
    pdf_processing_date: Optional[datetime] = Field(None, description="PDF 处理时间")

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
    #这个类让模型可以直接读取前面数据库的paper对象，同时可以被response直接解析

class PaperSearchResponse(BaseModel):
    papers: List[PaperResponse]
    total: int
