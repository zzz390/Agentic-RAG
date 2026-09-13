from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import httpx
import pytest
from src.exceptions import ArxivAPIException, ArxivAPITimeoutError, ArxivParseError, PDFDownloadException, PDFDownloadTimeoutError
from src.schemas.arxiv.paper import ArxivPaper
from src.services.arxiv.client import ArxivClient
from src.services.arxiv.factory import make_arxiv_client


class TestArxivClient:
    """ArxivClient 功能相关测试。"""

    @pytest.fixture
    def arxiv_client(self):
        """创建测试用 ArxivClient 实例。"""
        from src.config import ArxivSettings

        settings = ArxivSettings(
            base_url="https://export.arxiv.org/api/query",
            search_category="cs.AI",
            max_results=10,
            rate_limit_delay=0.1,  # Faster for tests
            timeout_seconds=5,
            pdf_cache_dir="/tmp/test_arxiv_cache",
        )
        return ArxivClient(settings)

    @pytest.fixture
    def mock_arxiv_response(self):
        """模拟 arXiv API XML 响应。"""
        return """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2024.0001v1</id>
            <updated>2024-01-01T00:00:00Z</updated>
            <published>2024-01-01T00:00:00Z</published>
            <title>Test Paper Title</title>
            <summary>Test abstract content</summary>
            <author><name>Test Author</name></author>
            <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom" term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
            <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
            <link title="pdf" href="http://arxiv.org/pdf/2024.0001v1" rel="alternate" type="application/pdf"/>
          </entry>
        </feed>"""

    def test_factory_creates_client(self):
        """工厂应创建 ArxivClient 实例。"""
        client = make_arxiv_client()
        assert isinstance(client, ArxivClient)
        assert client.search_category == "cs.AI"
        assert client.max_results == 15  # Default from ArxivSettings

    @pytest.mark.asyncio
    async def test_fetch_papers_success(self, arxiv_client, mock_arxiv_response):
        """应能成功拉取论文列表。"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = mock_arxiv_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            papers = await arxiv_client.fetch_papers(max_results=1)

            assert len(papers) == 1
            assert papers[0].arxiv_id == "2024.0001v1"
            assert papers[0].title == "Test Paper Title"
            assert papers[0].abstract == "Test abstract content"
            assert papers[0].authors == ["Test Author"]
            assert papers[0].categories == ["cs.AI"]

    @pytest.mark.asyncio
    async def test_fetch_papers_with_date_filters(self, arxiv_client, mock_arxiv_response):
        """带日期过滤的拉取应在 URL 中包含 submittedDate。"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = mock_arxiv_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            papers = await arxiv_client.fetch_papers(max_results=1, from_date="20240101", to_date="20240131")

            assert len(papers) == 1
            # 请求 URL 应包含日期过滤
            call_args = mock_client.return_value.__aenter__.return_value.get.call_args[0][0]
            assert "submittedDate:[202401010000+TO+202401312359]" in call_args

    @pytest.mark.asyncio
    async def test_fetch_papers_http_timeout(self, arxiv_client):
        """HTTP 超时应抛出 ArxivAPITimeoutError。"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("Request timeout")
            )

            with pytest.raises(ArxivAPITimeoutError) as exc_info:
                await arxiv_client.fetch_papers(max_results=1)

            assert "arXiv API request timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_papers_http_error(self, arxiv_client):
        """HTTP 状态错误应抛出 ArxivAPIException。"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_response)
            )

            with pytest.raises(ArxivAPIException) as exc_info:
                await arxiv_client.fetch_papers(max_results=1)

            assert "arXiv API returned error 500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_paper_by_id_success(self, arxiv_client, mock_arxiv_response):
        """应能按 arxiv_id 拉取单篇论文。"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = mock_arxiv_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            paper = await arxiv_client.fetch_paper_by_id("2024.0001v1")

            assert paper is not None
            assert paper.arxiv_id == "2024.0001v1"
            assert paper.title == "Test Paper Title"

    @pytest.mark.asyncio
    async def test_fetch_paper_by_id_not_found(self, arxiv_client):
        """单篇不存在时应返回 None。"""
        empty_response = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        </feed>"""

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = empty_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            paper = await arxiv_client.fetch_paper_by_id("nonexistent")

            assert paper is None

    def test_parse_response_invalid_xml(self, arxiv_client):
        """非法 XML 应抛出 ArxivParseError。"""
        invalid_xml = "This is not valid XML"

        with pytest.raises(ArxivParseError) as exc_info:
            arxiv_client._parse_response(invalid_xml)

        assert "Failed to parse arXiv XML response" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_download_pdf_cached(self, arxiv_client):
        """缓存命中时不应重复下载 PDF。"""
        paper = ArxivPaper(
            arxiv_id="2024.0001v1",
            title="Test Paper",
            authors=["Test Author"],
            abstract="Test abstract",
            categories=["cs.AI"],
            published_date="2024-01-01T00:00:00Z",
            pdf_url="http://arxiv.org/pdf/2024.0001v1",
        )

        with patch("pathlib.Path.exists", return_value=True):
            pdf_path = await arxiv_client.download_pdf(paper)

            assert pdf_path is not None
            assert pdf_path.name == "2024.0001v1.pdf"

    def test_rate_limiting(self, arxiv_client):
        """限流相关字段应正确初始化。"""
        import time

        # mock 上次请求时间
        arxiv_client._last_request_time = time.time() - 1.0  # 1 second ago

        # 生产环境会触发限流等待
        # 测试中仅校验限流字段存在
        assert arxiv_client.rate_limit_delay == 0.1  # Our test value
        assert arxiv_client._last_request_time is not None
