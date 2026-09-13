from pydantic import BaseModel, Field


class PostgreSQLSettings(BaseModel):
    database_url: str = Field(
        default="postgresql://rag_user:rag_password@localhost:5432/rag_db",
        description="PostgreSQL 连接 URL",
    )
    echo_sql: bool = Field(default=False, description="是否打印 SQL 日志")
    pool_size: int = Field(default=20, description="连接池大小")
    max_overflow: int = Field(default=0, description="连接池最大溢出连接数")
