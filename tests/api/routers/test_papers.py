"""API 单元测试：论文全文与摘要转换。"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.repositories.paper import PaperRepository
from src.routers.papers import _get_paper_by_key, _resolve_source_type, _to_full_response, _to_summary


def _sample_paper(*, arxiv_id: str = "1706.03762", raw_text: str = "Full paper text."):
    paper = MagicMock()
    paper.id = uuid4()
    paper.arxiv_id = arxiv_id
    paper.title = "Attention Is All You Need"
    paper.authors = ["Author One"]
    paper.abstract = "Abstract text."
    paper.categories = ["cs.CL"]
    paper.published_date = datetime(2017, 6, 12, tzinfo=timezone.utc)
    paper.pdf_url = "https://arxiv.org/pdf/1706.03762.pdf"
    paper.pdf_processed = True
    paper.raw_text = raw_text
    paper.sections = [{"title": "Introduction", "content": "Intro"}]
    paper.references = None
    paper.parser_used = "docling"
    paper.parser_metadata = {"source_type": "arxiv"}
    paper.pdf_processing_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    paper.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    paper.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return paper


def test_resolve_source_type_arxiv():
    paper = _sample_paper()
    assert _resolve_source_type(paper) == "arxiv"


def test_resolve_source_type_upload():
    paper = _sample_paper(arxiv_id="upload-abc-123")
    paper.parser_metadata = {"source_type": "upload"}
    assert _resolve_source_type(paper) == "upload"


def test_to_full_response_include_full_text_flag():
    paper = _sample_paper()
    with_text = _to_full_response(paper, include_full_text=True)
    without_text = _to_full_response(paper, include_full_text=False)

    assert with_text.raw_text == "Full paper text."
    assert without_text.raw_text is None
    assert without_text.sections is not None
    assert _to_summary(paper).has_full_text is True


def test_get_paper_by_key_prefers_uuid():
    paper = _sample_paper()
    repo = MagicMock(spec=PaperRepository)
    repo.get_by_id.return_value = paper
    repo.get_by_arxiv_id.return_value = None

    result = _get_paper_by_key(repo, str(paper.id))
    assert result is paper
    repo.get_by_id.assert_called_once()


def test_get_paper_by_key_falls_back_to_arxiv_id():
    paper = _sample_paper()
    repo = MagicMock(spec=PaperRepository)
    repo.get_by_id.return_value = None
    repo.get_by_arxiv_id.return_value = paper

    result = _get_paper_by_key(repo, "1706.03762")
    assert result is paper
    repo.get_by_arxiv_id.assert_called_once_with("1706.03762")


@pytest.mark.asyncio
async def test_get_paper_endpoint(client, monkeypatch):
    paper = _sample_paper()
    mock_repo = MagicMock()
    mock_repo.get_by_arxiv_id.return_value = paper
    mock_repo.get_by_id.return_value = None

    monkeypatch.setattr("src.routers.papers.PaperRepository", lambda session: mock_repo)

    response = await client.get("/api/v1/papers/1706.03762")
    assert response.status_code == 200
    data = response.json()
    assert data["arxiv_id"] == "1706.03762"
    assert data["raw_text"] == "Full paper text."
    assert data["source_type"] == "arxiv"


@pytest.mark.asyncio
async def test_get_paper_not_found(client, monkeypatch):
    mock_repo = MagicMock()
    mock_repo.get_by_arxiv_id.return_value = None
    mock_repo.get_by_id.return_value = None
    monkeypatch.setattr("src.routers.papers.PaperRepository", lambda session: mock_repo)

    response = await client.get("/api/v1/papers/missing-id")
    assert response.status_code == 404
