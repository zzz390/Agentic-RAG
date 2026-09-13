'''
论文数据库操作仓储类
create：接收 PaperCreate对象，转换成数据库模型并插入新论文记录。
upsert：最常用的写入方法。根据arxiv_id判断：不存在则创建，已存在则更新，避免重复数据。
基础查询：get_by_arxiv_id、get_by_id、get_all（分页查询，按发布日期倒序）、get_count（统计总数量）
按处理状态筛选：get_processed_papers、get_unprocessed_papers、get_papers_with_raw_text（已成功提取文本的论文）
统计数据：get_processing_stats，返回论文总数、已处理PDF数量、已提取文本数量、处理率、文本提取率
更新数据：update：接收已修改的Paper对象，提交变更并刷新数据库状态
'''

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from src.models.paper import Paper
from src.schemas.arxiv.paper import PaperCreate


class PaperRepository:
    def __init__(self, session: Session):
        self.session = session
        #self.session是SQLAlchemy中的数据库会话（Session），
        # 是数据库之间的临时对话通道，增删改查都由它来操作

    def create(self, paper: PaperCreate) -> Paper:
        db_paper = Paper(**paper.model_dump()) #model_dump() 是 Pydantic v2 中 BaseModel 提供的方法，作用是将 Pydantic 模型实例转换为一个 Python 字典（dict）
        self.session.add(db_paper)
        self.session.commit()
        self.session.refresh(db_paper)
        return db_paper

    def get_by_arxiv_id(self, arxiv_id: str) -> Optional[Paper]:
        stmt = select(Paper).where(Paper.arxiv_id == arxiv_id)
        return self.session.scalar(stmt)

    def get_by_id(self, paper_id: UUID) -> Optional[Paper]:
        stmt = select(Paper).where(Paper.id == paper_id)
        return self.session.scalar(stmt)

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        stmt = select(Paper).order_by(Paper.published_date.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def get_count(self) -> int:
        stmt = select(func.count(Paper.id))
        return self.session.scalar(stmt) or 0

    def get_processed_papers(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        stmt = (
            select(Paper)
            .where(Paper.pdf_processed == True)
            .order_by(Paper.pdf_processing_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt))

    def get_unprocessed_papers(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        stmt = select(Paper).where(Paper.pdf_processed == False).order_by(Paper.published_date.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def get_papers_with_raw_text(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        stmt = select(Paper).where(Paper.raw_text != None).order_by(Paper.pdf_processing_date.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def get_processing_stats(self) -> dict:
        total_papers = self.get_count()

        processed_stmt = select(func.count(Paper.id)).where(Paper.pdf_processed == True)
        processed_papers = self.session.scalar(processed_stmt) or 0

        text_stmt = select(func.count(Paper.id)).where(Paper.raw_text != None)
        papers_with_text = self.session.scalar(text_stmt) or 0

        return {
            "total_papers": total_papers,
            "processed_papers": processed_papers,
            "papers_with_text": papers_with_text,
            "processing_rate": (processed_papers / total_papers * 100) if total_papers > 0 else 0,
            "text_extraction_rate": (papers_with_text / processed_papers * 100) if processed_papers > 0 else 0,
        }

    def update(self, paper: Paper) -> Paper:
        self.session.add(paper)
        self.session.commit()
        self.session.refresh(paper)
        return paper

    def upsert(self, paper_create: PaperCreate) -> Paper:
        existing_paper = self.get_by_arxiv_id(paper_create.arxiv_id)
        if existing_paper:
            for key, value in paper_create.model_dump(exclude_unset=True).items():
                setattr(existing_paper, key, value)
            return self.update(existing_paper)
        else:
            return self.create(paper_create)
