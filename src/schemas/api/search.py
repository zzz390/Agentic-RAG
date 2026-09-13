'''
论文搜索功能的全套API数据格式规范
统一前后端搜索接口的规范
定义前端怎么发起搜索，定义后端返回什么结果，自动校验+自动生成接口文档
'''
from typing import List, Optional

from pydantic import BaseModel, Field

#普通搜索请求体
#普通搜索的前端请求格式
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="检索关键词（标题、摘要、作者）")
    size: int = Field(default=10, ge=1, le=50, description="返回条数")
    from_: int = Field(default=0, ge=0, alias="from", description="分页偏移量")
    categories: Optional[List[str]] = Field(default=None, description="按分类筛选")
    latest_papers: bool = Field(default=False, description="按发表时间排序（最新优先），否则按相关度")

#混合搜索请求体
#混合搜索的前端请求格式
class HybridSearchRequest(BaseModel):
    query: str = Field(..., description="检索文本", min_length=1, max_length=500)
    size: int = Field(10, description="返回条数", ge=1, le=100)
    from_: int = Field(0, description="分页偏移量", ge=0, alias="from")
    categories: Optional[List[str]] = Field(None, description="arXiv 分类筛选，如 cs.AI、cs.LG")
    latest_papers: bool = Field(False, description="按发表时间排序，否则按相关度")
    use_hybrid: bool = Field(True, description="启用混合检索（BM25 + 向量，自动生成嵌入）")
    min_score: float = Field(0.0, description="最低相关度分数阈值", ge=0.0)

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "query": "machine learning neural networks",
                "size": 10,
                "categories": ["cs.AI", "cs.LG"],
                "latest_papers": False,
                "use_hybrid": True,
            }
        }

#单条搜索结果，返回一条论文结果
class SearchHit(BaseModel):
    arxiv_id: str
    title: str
    authors: Optional[str]
    abstract: Optional[str]
    published_date: Optional[str]
    pdf_url: Optional[str]
    score: float
    highlights: Optional[dict] = None

    chunk_text: Optional[str] = Field(None, description="匹配 chunk 的文本内容")
    chunk_id: Optional[str] = Field(None, description="chunk 唯一标识")
    section_name: Optional[str] = Field(None, description="chunk 所在章节名称")

#搜索接口最终返回，整个搜索接口返回的最外层结构
class SearchResponse(BaseModel):
    query: str
    total: int
    hits: List[SearchHit]
    size: int = Field(description="请求的返回条数")
    from_: int = Field(alias="from", description="使用的分页偏移量")
    search_mode: Optional[str] = Field(None, description="检索模式：bm25、vector 或 hybrid")
    error: Optional[str] = None

    class Config:
        populate_by_name = True
