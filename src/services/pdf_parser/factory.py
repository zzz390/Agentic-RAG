from functools import lru_cache

from src.config import get_settings

from .parser import PDFParserService

#全项目只创建一个PDFParserService，避免重复初始化浪费资源
@lru_cache(maxsize=1)
def make_pdf_parser_service() -> PDFParserService:
    settings = get_settings()
    return PDFParserService(
        max_pages=settings.pdf_parser.max_pages,
        max_file_size_mb=settings.pdf_parser.max_file_size_mb,
        do_ocr=settings.pdf_parser.do_ocr,
        do_table_structure=settings.pdf_parser.do_table_structure,
    )
