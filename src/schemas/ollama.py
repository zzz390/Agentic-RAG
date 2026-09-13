from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class RAGResponse(BaseModel):
    answer: str = Field(description="基于所给论文片段的综合回答")
    sources: List[str] = Field(
        default_factory=list,
        description="回答所依据的论文 PDF 链接列表",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        default="medium",
        description="置信度：high / medium / low",
    )
    citations: List[str] = Field(
        default_factory=list,
        description="回答中引用的 arXiv ID 或论文标题",
    )
