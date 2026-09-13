from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ParserType(str, Enum):
#选择解析器，用docling这个库来解析PDF
    DOCLING = "docling"

class PaperSection(BaseModel):
#章节模型，把PDF解析出来的文本，按章节结构化存储
    title: str = Field(..., description="章节标题")
    content: str = Field(..., description="章节正文")
    level: int = Field(default=1, description="章节层级")

class PaperFigure(BaseModel):
#图片模型，用来描述论文里的图片、图表
    caption: str = Field(..., description="图注")
    id: str = Field(..., description="图标识")


class PaperTable(BaseModel):
#表格模型
    caption: str = Field(..., description="表注")
    id: str = Field(..., description="表标识")


class PdfContent(BaseModel):
#前面的内容会被存储在这里

    sections: List[PaperSection] = Field(default_factory=list, description="论文章节")
    figures: List[PaperFigure] = Field(default_factory=list, description="插图列表")
    tables: List[PaperTable] = Field(default_factory=list, description="表格列表")
    raw_text: str = Field(..., description="提取的全文")
    references: List[str] = Field(default_factory=list, description="参考文献")
    parser_used: ParserType = Field(..., description="用于提取的解析器")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="解析元数据")


class ArxivMetadata(BaseModel):
#arxiv元数据

    title: str = Field(..., description="arXiv 论文标题")
    authors: List[str] = Field(..., description="arXiv 作者列表")
    abstract: str = Field(..., description="arXiv 摘要")
    arxiv_id: str = Field(..., description="arXiv 标识")
    categories: List[str] = Field(default_factory=list, description="arXiv 分类")
    published_date: str = Field(..., description="发表日期")
    pdf_url: str = Field(..., description="PDF 下载地址")


class ParsedPaper(BaseModel):
#完整的论文数据模型

    arxiv_metadata: ArxivMetadata = Field(..., description="来自 arXiv API 的元数据")
    pdf_content: Optional[PdfContent] = Field(None, description="从 PDF 提取的内容")
