from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

#用户提问的安全校验评分结果，判断问题是否合规、违规等
class GuardrailScoring(BaseModel):
    score: int = Field(ge=0, le=100, description="相关度分数，0～100")
    reason: str = Field(description="打分理由简述")

#判断检索回来的论文是否有用，告诉系统要不要用这篇论文来生成答案
class GradeDocuments(BaseModel):
    binary_score: Literal["yes", "no"] = Field(description="文档是否相关：yes 或 no")
    reasoning: str = Field(default="", description="判定理由")

#一条论文来源信息，把论文的信息返回给前端
class SourceItem(BaseModel):
    arxiv_id: str = Field(description="arXiv 论文 ID")
    title: str = Field(description="论文标题")
    authors: List[str] = Field(default_factory=list, description="作者列表")
    url: str = Field(description="论文链接")
    relevance_score: float = Field(default=0.0, description="检索相关度分数")

    def to_dict(self) -> Dict[str, Any]:
        #把对象转为字典
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "url": self.url,
            "relevance_score": self.relevance_score,
        }

#工具调用返回的结果包，智能体调用工具之后把工具、结果元数据打包，让系统知道谁在干活
class ToolArtefact(BaseModel):
    tool_name: str = Field(description="工具名称")
    tool_call_id: str = Field(description="工具调用唯一 ID")
    content: Any = Field(description="工具返回内容")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加元数据")

#智能体路线决策，决定智能体下一步做什么，是智能体的大脑决策
class RoutingDecision(BaseModel):
    route: Literal["retrieve", "out_of_scope", "generate_answer", "rewrite_query"] = Field(
        description="下一跳路由节点"
    )
    reason: str = Field(default="", description="路由原因说明")

#文档评分详细结果
class GradingResult(BaseModel):
    document_id: str = Field(description="文档标识")
    is_relevant: bool = Field(description="是否相关")
    score: float = Field(default=0.0, description="相关度分数")
    reasoning: str = Field(default="", description="评分理由")

#记录智能体的思考步骤
class ReasoningStep(BaseModel):
    step_name: str = Field(description="推理步骤名称")
    description: str = Field(description="步骤说明")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="步骤元数据")
