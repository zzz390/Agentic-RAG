'''
API健康检查接口的数据格式标准
用来定义服务启动后，健康检查接口返回的JSON结构
'''
from typing import Dict, Optional

from pydantic import BaseModel, Field


#定义单个服务的健康状态
class ServiceStatus(BaseModel):
    status: str = Field(..., description="服务状态", example="healthy")
    message: Optional[str] = Field(None, description="状态说明", example="Connected successfully")

#整体健康响应
class HealthResponse(BaseModel):
    status: str = Field(..., description="整体健康状态", example="ok")
    version: str = Field(..., description="应用版本", example="0.1.0")
    environment: str = Field(..., description="运行环境", example="development")
    service_name: str = Field(..., description="服务名称", example="rag-api")
    services: Optional[Dict[str, ServiceStatus]] = Field(None, description="各依赖组件状态")

    #展示实例JSON
    class Config:
        json_schema_extra = {
            "example": {
                "status": "ok",
                "version": "0.1.0",
                "environment": "development",
                "service_name": "rag-api",
                "services": {
                    "database": {"status": "healthy", "message": "Connected successfully"},
                    "pdf_parser": {"status": "healthy", "message": "Docling parser ready"},
                },
            }
        }
