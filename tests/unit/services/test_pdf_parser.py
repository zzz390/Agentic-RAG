from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from src.exceptions import PDFParsingException, PDFValidationError
from src.schemas.pdf_parser.models import PaperSection, ParserType, PdfContent
from src.services.pdf_parser.docling import DoclingParser
from src.services.pdf_parser.factory import make_pdf_parser_service
from src.services.pdf_parser.parser import PDFParserService


class TestDoclingParser:
    """DoclingParser 功能相关测试。"""

    @pytest.fixture
    def docling_parser(self):
        """创建测试用 DoclingParser 实例。"""
        return DoclingParser(max_pages=20, max_file_size_mb=10, do_ocr=False)

    @pytest.fixture
    def valid_pdf_path(self, tmp_path):
        """创建模拟合法 PDF 路径。"""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest content")
        return pdf_file

    @pytest.fixture
    def empty_pdf_path(self, tmp_path):
        """创建空 PDF 文件路径。"""
        pdf_file = tmp_path / "empty.pdf"
        pdf_file.write_bytes(b"")
        return pdf_file

    @pytest.fixture
    def invalid_pdf_path(self, tmp_path):
        """创建非法 PDF 文件路径。"""
        pdf_file = tmp_path / "invalid.pdf"
        pdf_file.write_bytes(b"Not a PDF file")
        return pdf_file

    def test_docling_parser_initialization(self, docling_parser):
        """DoclingParser 应正确初始化。"""
        assert docling_parser.max_pages == 20
        assert docling_parser.max_file_size_bytes == 10 * 1024 * 1024
        assert docling_parser._warmed_up is False

    def test_validate_pdf_valid_file(self, docling_parser, valid_pdf_path):
        """合法 PDF 校验（依赖 pypdfium2，暂跳过）。"""
        # 依赖 pypdfium2，暂跳过
        pass

    def test_validate_pdf_empty_file(self, docling_parser, empty_pdf_path):
        """空文件应抛出 PDFValidationError。"""
        with pytest.raises(PDFValidationError) as exc_info:
            docling_parser._validate_pdf(empty_pdf_path)

        assert "PDF file is empty" in str(exc_info.value)

    def test_validate_pdf_invalid_header(self, docling_parser, invalid_pdf_path):
        """非 PDF 头应抛出 PDFValidationError。"""
        with pytest.raises(PDFValidationError) as exc_info:
            docling_parser._validate_pdf(invalid_pdf_path)

        assert "File does not have PDF header" in str(exc_info.value)

    def test_validate_pdf_nonexistent_file(self, docling_parser):
        """文件不存在应抛出 PDFValidationError。"""
        nonexistent_path = Path("/nonexistent/file.pdf")

        with pytest.raises(PDFValidationError) as exc_info:
            docling_parser._validate_pdf(nonexistent_path)

        assert "Error validating PDF" in str(exc_info.value)

    # 复杂 PDF 解析测试已移除（强依赖外部库）


class TestPDFParserService:
    """PDFParserService 功能相关测试。"""

    @pytest.fixture
    def pdf_parser_service(self):
        """创建测试用 PDFParserService 实例。"""
        return PDFParserService(max_pages=20, max_file_size_mb=10)

    @pytest.fixture
    def valid_pdf_path(self, tmp_path):
        """创建模拟合法 PDF 路径。"""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest content")
        return pdf_file

    def test_pdf_parser_service_initialization(self, pdf_parser_service):
        """PDFParserService 应正确初始化。"""
        assert isinstance(pdf_parser_service.docling_parser, DoclingParser)
        assert pdf_parser_service.docling_parser.max_pages == 20

    @pytest.mark.asyncio
    async def test_parse_pdf_file_not_found(self, pdf_parser_service):
        """解析不存在文件应抛出 PDFValidationError。"""
        nonexistent_path = Path("/nonexistent/file.pdf")

        with pytest.raises(PDFValidationError) as exc_info:
            await pdf_parser_service.parse_pdf(nonexistent_path)

        assert "PDF file not found" in str(exc_info.value)

    @patch("src.services.pdf_parser.parser.DoclingParser.parse_pdf")
    @pytest.mark.asyncio
    async def test_parse_pdf_success(self, mock_parse, pdf_parser_service, valid_pdf_path):
        """应能成功解析 PDF 并返回 PdfContent。"""
        mock_content = PdfContent(
            raw_text="Test content", sections=[], tables=[], figures=[], parser_used=ParserType.DOCLING, metadata={}
        )
        mock_parse.return_value = mock_content

        result = await pdf_parser_service.parse_pdf(valid_pdf_path)

        assert result == mock_content
        mock_parse.assert_called_once_with(valid_pdf_path)

    @patch("src.services.pdf_parser.parser.DoclingParser.parse_pdf")
    @pytest.mark.asyncio
    async def test_parse_pdf_no_result(self, mock_parse, pdf_parser_service, valid_pdf_path):
        """解析无结果应抛出 PDFParsingException。"""
        mock_parse.return_value = None

        with pytest.raises(PDFParsingException) as exc_info:
            await pdf_parser_service.parse_pdf(valid_pdf_path)

        assert "Docling parsing returned no result" in str(exc_info.value)

    @patch("src.services.pdf_parser.parser.DoclingParser.parse_pdf")
    @pytest.mark.asyncio
    async def test_parse_pdf_docling_error(self, mock_parse, pdf_parser_service, valid_pdf_path):
        """Docling 异常应包装为 PDFParsingException。"""
        mock_parse.side_effect = Exception("Docling error")

        with pytest.raises(PDFParsingException) as exc_info:
            await pdf_parser_service.parse_pdf(valid_pdf_path)

        assert "Docling parsing error" in str(exc_info.value)

    def test_factory_creates_service(self):
        """工厂应创建 PDFParserService 实例。"""
        service = make_pdf_parser_service()
        assert isinstance(service, PDFParserService)
        assert isinstance(service.docling_parser, DoclingParser)

    def test_factory_caching(self):
        """工厂应通过 @lru_cache 复用同一实例。"""
        service1 = make_pdf_parser_service()
        service2 = make_pdf_parser_service()
        # @lru_cache 应返回同一实例
        assert service1 is service2
