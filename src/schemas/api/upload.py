from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    document_id: UUID = Field(..., description="文档内部 UUID")
    arxiv_id: str = Field(..., description="检索与 API 使用的文档标识（upload-{uuid}）")
    title: str = Field(..., description="入库后的文档标题")
    original_filename: str = Field(..., description="原始上传文件名")
    chunks_created: int = Field(..., description="生成的文本块数量")
    chunks_indexed: int = Field(..., description="写入 OpenSearch 的块数量")
    embeddings_generated: int = Field(..., description="生成的向量嵌入数量")
    parser_used: str = Field(..., description="使用的解析器")
    status: Literal["indexed", "partial", "failed"] = Field(..., description="入库结果状态")
    message: Optional[str] = Field(None, description="可读的状态说明")

    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "arxiv_id": "upload-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "title": "示例上传文档",
                "original_filename": "notes.pdf",
                "chunks_created": 12,
                "chunks_indexed": 12,
                "embeddings_generated": 12,
                "parser_used": "docling",
                "status": "indexed",
                "message": "文档已成功入库并建立索引",
            }
        }
