import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from src.db.interfaces.postgresql import Base


class Paper(Base):
    __tablename__ = "papers"
    #要建一张表叫papers，会在执行database.startup()的时候自动创建

    # UUID全球唯一随机ID，不会重复的身份证号、arxiv论文编号、标题、作者、摘要、分类、发布时间、PDF下载地址
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #as_uuid=True意思是在Python里，它会被自动转成uuid.UUID对象，primary_key=True表示这个字段是主键
    #default=uuid.uuid4表示如果没有给id，自动生成默认值
    #Column定义数据库表的一列（字段）
    #这个UUID是存数据的时候系统发的，不是本身论文就有的
    arxiv_id = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=False)
    authors = Column(JSON, nullable=False)
    abstract = Column(Text, nullable=False)
    categories = Column(JSON, nullable=False)
    published_date = Column(DateTime, nullable=False)
    pdf_url = Column(String, nullable=False)
    #nullable=False表示不能为空，index=True表示创建索引
    #UUID是系统发的，但是这些标题要自己填，后续有别的代码负责填

    #PDF原始文本、章节结构、参考文献
    raw_text = Column(Text, nullable=True)
    sections = Column(JSON, nullable=True)
    references = Column(JSON, nullable=True)

    #用了哪个解析器、解析器信息、是否已解析、处理时间
    #系统只能拿到PDF，但是里面都是二进制，会乱码，所以需要解析器，同时有图片、表格等就需要不同的解析器
    parser_used = Column(String, nullable=True)
    parser_metadata = Column(JSON, nullable=True)
    pdf_processed = Column(Boolean, default=False, nullable=False)
    pdf_processing_date = Column(DateTime, nullable=True)

    #系统时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
