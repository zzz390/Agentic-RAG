from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import UploadSettings
from src.exceptions import UploadParsingException, UploadValidationError
from src.schemas.pdf_parser.models import ParserType, PdfContent
from src.services.document_upload.service import UploadDocumentService


@pytest.fixture
def upload_settings(tmp_path):
    return UploadSettings(
        upload_dir=str(tmp_path / "uploads"),
        max_file_size_mb=5,
        allowed_extensions=[".pdf", ".txt", ".md", ".docx", ".xlsx", ".xls"],
        excel_max_rows=10,
        min_extracted_text_chars=10,
    )


@pytest.fixture
def pdf_parser():
    parser = MagicMock()
    parser.parse_pdf = AsyncMock()
    return parser


@pytest.fixture
def service(pdf_parser, upload_settings):
    return UploadDocumentService(pdf_parser=pdf_parser, upload_settings=upload_settings)


@pytest.mark.asyncio
async def test_parse_txt_file(service, upload_settings, tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("这是 UploadDocumentService 的单元测试文本内容。", encoding="utf-8")

    result = await service.parse_file(text_file)

    assert result.parser_used.value == "txt"
    assert "单元测试文本内容" in result.raw_text
    assert result.file_extension == ".txt"


@pytest.mark.asyncio
async def test_parse_pdf_file(service, pdf_parser, tmp_path):
    pdf_file = tmp_path / "paper.pdf"
    pdf_file.write_bytes(b"%PDF-1.4")

    pdf_parser.parse_pdf.return_value = PdfContent(
        raw_text="PDF 解析后的正文内容用于上传测试。",
        parser_used=ParserType.DOCLING,
        sections=[],
    )

    result = await service.parse_file(pdf_file, original_filename="paper.pdf")

    assert result.parser_used.value == "docling"
    assert "PDF 解析后的正文内容" in result.raw_text
    pdf_parser.parse_pdf.assert_awaited_once_with(pdf_file)


@pytest.mark.asyncio
async def test_parse_missing_file_raises(service, tmp_path):
    missing = tmp_path / "missing.txt"

    with pytest.raises(UploadValidationError):
        await service.parse_file(missing)


@pytest.mark.asyncio
async def test_parse_pdf_failure_raises(service, pdf_parser, tmp_path):
    pdf_file = tmp_path / "broken.pdf"
    pdf_file.write_bytes(b"%PDF-1.4")
    pdf_parser.parse_pdf.side_effect = RuntimeError("docling failed")

    with pytest.raises(UploadParsingException):
        await service.parse_file(pdf_file)
