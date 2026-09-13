'''
API数据格式标准
定义前端传什么、定义后端返回什么、自动生成接口文档+自动校验数据
'''
from typing import List, Optional

from pydantic import BaseModel, Field

#用户提问的请求体
#定义用户提问时，前端必须传给后端的数据格式
class AskRequest(BaseModel):
    query: str = Field(..., description="用户问题", min_length=1, max_length=1000)
    top_k: int = Field(3, description="检索返回的 chunk 数量", ge=1, le=10)
    use_hybrid: bool = Field(True, description="是否启用混合检索（BM25 + 向量）")
    model: str = Field("qwen3.8-flash", description="大模型服务所用模型名")
    categories: Optional[List[str]] = Field(None, description="按 arXiv 分类筛选")
    user_id: str = Field("local_user", description="用户标识，用于隔离长期记忆", min_length=1, max_length=128)
    session_id: Optional[str] = Field(None, description="会话标识；客户端复用该值即可多轮对话", max_length=128)
    enable_memory: bool = Field(True, description="是否启用 Redis 短期记忆与 PostgreSQL 长期记忆")
    include_contexts: bool = Field(False, description="是否返回实际检索上下文；仅建议离线评测使用")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "这篇论文的主要结论是什么？",
                "top_k": 3,
                "use_hybrid": True,
                "model": "qwen3.8-flash",
                "categories": ["cs.AI", "cs.LG"],
            }
        }

#普通问答返回体
#定义后端返回给前端的标准格式
class AskResponse(BaseModel):
    query: str = Field(..., description="用户原始问题")
    answer: str = Field(..., description="大模型生成的回答")
    sources: List[str] = Field(..., description="引用来源（PDF 链接等）")
    chunks_used: int = Field(..., description="参与生成的 chunk 数量")
    search_mode: str = Field(..., description="检索模式：bm25 或 hybrid")
    session_id: Optional[str] = Field(None, description="本次对话的会话标识")
    memory_used: bool = Field(False, description="本次回答是否读取了历史记忆")
    short_term_messages: int = Field(0, description="读取的当前会话消息数")
    long_term_messages: int = Field(0, description="读取的跨会话消息数")
    retrieved_contexts: List[str] = Field(default_factory=list, description="本次生成使用的检索上下文，仅评测模式返回")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "这篇论文的主要结论是什么？",
                "answer": "根据文档片段，主要结论是……",
                "sources": ["https://arxiv.org/pdf/1706.03762.pdf"],
                "chunks_used": 3,
                "search_mode": "hybrid",
            }
        }

#智能体问答返回体
#继承AskResponse，比普通问答多了agent的内容
class AgenticAskResponse(AskResponse):
    reasoning_steps: List[str] = Field(..., description="智能体推理步骤说明")
    retrieval_attempts: int = Field(..., description="文档检索尝试次数")
    rewritten_query: Optional[str] = Field(None, description="智能体为提高召回率生成的改写查询")
    trace_id: Optional[str] = Field(None, description="Langfuse 追踪 ID，用于反馈与调试")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "这篇论文的主要结论是什么？",
                "answer": "根据检索到的文档……",
                "sources": ["https://arxiv.org/pdf/1706.03762.pdf"],
                "chunks_used": 3,
                "search_mode": "hybrid",
                "reasoning_steps": [
                    "判断需要检索相关文档",
                    "从 OpenSearch 检索片段",
                    "根据相关片段生成回答",
                ],
                "retrieval_attempts": 1,
                "trace_id": "abc123-def456-ghi789",
            }
        }

#用户反馈请求
#用户对答案进行反馈打分
class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., description="响应中的 Langfuse trace ID")
    score: float = Field(..., description="反馈分数（0～1 或 -1～1）", ge=-1, le=1)
    comment: Optional[str] = Field(None, description="可选文字反馈", max_length=1000)

    class Config:
        json_schema_extra = {
            "example": {
                "trace_id": "abc123-def456-ghi789",
                "score": 1.0,
                "comment": "回答准确、有帮助",
            }
        }


#反馈结果返回
#返回是否记录反馈
class FeedbackResponse(BaseModel):
    success: bool = Field(..., description="是否成功记录反馈")
    message: str = Field(..., description="状态说明")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "反馈已记录",
            }
        }
