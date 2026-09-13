import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from src.dependencies import SessionDep
from src.models.paper import Paper
from src.repositories.paper import PaperRepository
from src.schemas.api.papers import PaperFullResponse, PaperListResponse, PaperSummary

logger = logging.getLogger(__name__)

router = APIRouter(tags=["论文"])


def _resolve_source_type(paper: Paper) -> str:
    if paper.arxiv_id.startswith("upload-"):
        return "upload"
    metadata = paper.parser_metadata or {}
    return metadata.get("source_type", "arxiv")


def _to_summary(paper: Paper) -> PaperSummary:
    return PaperSummary(
        id=paper.id,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        authors=paper.authors,
        abstract=paper.abstract,
        categories=paper.categories,
        source_type=_resolve_source_type(paper),
        pdf_url=paper.pdf_url,
        pdf_processed=paper.pdf_processed,
        has_full_text=bool(paper.raw_text and paper.raw_text.strip()),
        published_date=paper.published_date,
    )


def _to_full_response(paper: Paper, include_full_text: bool) -> PaperFullResponse:
    summary = _to_summary(paper)
    return PaperFullResponse(
        **summary.model_dump(),
        raw_text=paper.raw_text if include_full_text else None,
        sections=paper.sections,
        references=paper.references,
        parser_used=paper.parser_used,
        parser_metadata=paper.parser_metadata,
        pdf_processing_date=paper.pdf_processing_date,
        created_at=paper.created_at,
        updated_at=paper.updated_at,
    )


def _get_paper_by_key(repo: PaperRepository, document_key: str) -> Optional[Paper]:
    try:
        paper_id = UUID(document_key)
    except ValueError:
        paper_id = None

    if paper_id is not None:
        paper = repo.get_by_id(paper_id)
        if paper is not None:
            return paper

    return repo.get_by_arxiv_id(document_key)


@router.get("/papers", response_model=PaperListResponse)
async def list_papers(
    session: SessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source_type: Optional[Literal["arxiv", "upload"]] = Query(
        None,
        description="按来源筛选：arxiv 或 upload",
    ),
) -> PaperListResponse:
    """列出 PostgreSQL 中已入库的文档（元数据及是否含全文）。"""
    repo = PaperRepository(session)
    papers = repo.get_all(limit=limit, offset=offset)
    total = repo.get_count()

    if source_type:
        papers = [paper for paper in papers if _resolve_source_type(paper) == source_type]

    return PaperListResponse(
        papers=[_to_summary(paper) for paper in papers],
        total=total if source_type is None else len(papers),
        limit=limit,
        offset=offset,
    )


@router.get("/papers/{document_key}", response_model=PaperFullResponse)
async def get_paper(
    document_key: str,
    session: SessionDep,
    include_full_text: bool = Query(
        True,
        description="是否包含 raw_text 正文；false 时仅返回元数据与 sections",
    ),
) -> PaperFullResponse:
    """
    按 arXiv ID（如 1706.03762）、上传 ID（upload-{uuid}）或内部 UUID 浏览文档。

    全文保存在 PostgreSQL；OpenSearch 存可检索的 chunk，供 RAG 使用。
    """
    repo = PaperRepository(session)
    paper = _get_paper_by_key(repo, document_key)

    if paper is None:
        raise HTTPException(status_code=404, detail=f"未找到文档: {document_key}")

    logger.info("Paper browse request for %s (include_full_text=%s)", paper.arxiv_id, include_full_text)
    return _to_full_response(paper, include_full_text=include_full_text)
