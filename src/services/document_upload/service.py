import logging
from pathlib import Path
from typing import Optional

from src.config import UploadSettings
from src.exceptions import PDFParsingException, PDFValidationError, UploadParsingException
from src.services.pdf_parser.parser import PDFParserService

from .loader import (
    derive_title_hint,
    extract_by_extension,
    parse_pdf_content,
    validate_upload_file,
)
from .models import ParsedUploadDocument, UploadParserType

logger = logging.getLogger(__name__)


class UploadDocumentService:
    """解析用户上传文件为结构化文本，供下游入库（阶段 2）。"""

    def __init__(self, pdf_parser: PDFParserService, upload_settings: UploadSettings):
        self.pdf_parser = pdf_parser
        self.settings = upload_settings

    async def parse_file(
        self,
        file_path: Path,
        original_filename: Optional[str] = None,
        title_hint: Optional[str] = None,
    ) -> ParsedUploadDocument:
        """
        校验并解析上传文件。

        PDF 经 PDFParserService 走 Docling；其他格式使用 loader.py 中的轻量提取器。
        """
        validate_upload_file(file_path, self.settings)

        display_name = original_filename or file_path.name
        extension = file_path.suffix.lower()
        resolved_title = derive_title_hint(file_path, title_hint)

        logger.info("Parsing uploaded file: %s (%s)", display_name, extension)

        if extension == ".pdf":
            return await self._parse_pdf(file_path, display_name, resolved_title, title_hint)

        raw_text, parser_used, sections, metadata = extract_by_extension(
            file_path=file_path,
            settings=self.settings,
            title_hint=title_hint,
        )
        metadata.setdefault("title_hint", resolved_title)

        return ParsedUploadDocument(
            raw_text=raw_text,
            sections=sections,
            parser_used=parser_used,
            metadata=metadata,
            original_filename=display_name,
            file_extension=extension,
            title_hint=metadata.get("title_hint", resolved_title),
        )

    async def _parse_pdf(
        self,
        file_path: Path,
        display_name: str,
        resolved_title: str,
        title_hint: Optional[str],
    ) -> ParsedUploadDocument:
        try:
            pdf_content = await self.pdf_parser.parse_pdf(file_path)
        except (PDFValidationError, PDFParsingException) as exc:
            raise UploadParsingException(f"PDF parsing failed for '{display_name}': {exc}") from exc
        except Exception as exc:
            raise UploadParsingException(f"Unexpected PDF parsing error for '{display_name}': {exc}") from exc

        if pdf_content is None:
            raise UploadParsingException(f"PDF parsing returned no content for '{display_name}'")

        raw_text, sections, metadata = parse_pdf_content(
            pdf_content=pdf_content,
            file_path=file_path,
            settings=self.settings,
            title_hint=title_hint,
        )
        metadata.setdefault("title_hint", resolved_title)

        return ParsedUploadDocument(
            raw_text=raw_text,
            sections=sections,
            parser_used=UploadParserType.DOCLING,
            metadata=metadata,
            original_filename=display_name,
            file_extension=".pdf",
            title_hint=metadata.get("title_hint", resolved_title),
        )
