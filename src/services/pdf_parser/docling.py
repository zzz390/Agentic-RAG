'''
DoclingParser是一个专业的论文PDF解析器
_warm_up_models只执行一次，模型预热
_validate_pdf做PDF安检。
parse_pdf调用上面两个函数，把PDF解析，返回结构化内容
'''
import logging
from pathlib import Path
from typing import Optional

import pypdfium2 as pdfium
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from src.exceptions import PDFParsingException, PDFValidationError
from src.schemas.pdf_parser.models import PaperFigure, PaperSection, PaperTable, ParserType, PdfContent

logger = logging.getLogger(__name__)


class DoclingParser:
    def __init__(self, max_pages: int, max_file_size_mb: int, do_ocr: bool = False, do_table_structure: bool = True):
        #do_ocr=False默认步开启图片文字识别只直解析DPF内的文字，do_table_structure=True：默认开启表格结构识别
        pipeline_options = PdfPipelineOptions(
            do_table_structure=do_table_structure,
            do_ocr=do_ocr,
        )

        self._converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)})
        #把刚刚的设置pipeline_options传给它，负责把PDF读进去然后拆成文字、标题、段落
        self._warmed_up = False
        #记录模型是否已经预热
        self.max_pages = max_pages
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

    def _warm_up_models(self):
    #以下划线开头，是一个私有方法，旨在类内部调用
        if not self._warmed_up:
            self._warmed_up = True

    #检查文件是否为空、检查文件大小是否超限、检查是不是真的PDF、检查PDF页数是否过多
    #对PDF做安检
    def _validate_pdf(self, pdf_path: Path) -> bool:
        try:
            if pdf_path.stat().st_size == 0:
                logger.error(f"PDF file is empty: {pdf_path}")
                raise PDFValidationError(f"PDF file is empty: {pdf_path}")

            file_size = pdf_path.stat().st_size
            if file_size > self.max_file_size_bytes:
                logger.warning(
                    f"PDF file size ({file_size / 1024 / 1024:.1f}MB) exceeds limit ({self.max_file_size_bytes / 1024 / 1024:.1f}MB), skipping processing"
                )
                raise PDFValidationError(
                    f"PDF file too large: {file_size / 1024 / 1024:.1f}MB > {self.max_file_size_bytes / 1024 / 1024:.1f}MB"
                )

            #查看文件头部，检查是否以%PDF开头
            with open(pdf_path, "rb") as f:
                header = f.read(8)
                if not header.startswith(b"%PDF-"):
                    logger.error(f"File does not have PDF header: {pdf_path}")
                    raise PDFValidationError(f"File does not have PDF header: {pdf_path}")

            pdf_doc = pdfium.PdfDocument(str(pdf_path))
            actual_pages = len(pdf_doc)
            pdf_doc.close()

            if actual_pages > self.max_pages:
                logger.warning(
                    f"PDF has {actual_pages} pages, exceeding limit of {self.max_pages} pages. Skipping processing to avoid performance issues."
                )
                raise PDFValidationError(f"PDF has too many pages: {actual_pages} > {self.max_pages}")

            return True

        except PDFValidationError:
            raise
        except Exception as e:
            logger.error(f"Error validating PDF {pdf_path}: {e}")
            raise PDFValidationError(f"Error validating PDF {pdf_path}: {e}")

    def parse_pdf(self, pdf_path: Path) -> Optional[PdfContent]:
        try:
            self._validate_pdf(pdf_path)
            self._warm_up_models()
            #检查PDF之后，把预热标签打开
            result = self._converter.convert(str(pdf_path), max_num_pages=self.max_pages, max_file_size=self.max_file_size_bytes)
            #然后放到converter里面拆开，变成结构化文档

            doc = result.document
            #把解析好的文档拿出来

            sections = []
            #创建空列表来存放论文章节
            current_section = {"title": "Content", "content": ""}

            for element in doc.texts:
                if hasattr(element, "label") and element.label in ["title", "section_header"]:
                #判断这段是不是标题/章节头，如果是，说明新章节开始
                    if current_section["content"].strip():
                        sections.append(PaperSection(title=current_section["title"], content=current_section["content"].strip()))
                    #如果上一章节有内容，就把上一张存入列表
                    current_section = {"title": element.text.strip(), "content": ""}
                    #开启新章节
                else:
                    if hasattr(element, "text") and element.text:
                        current_section["content"] += element.text + "\n"
                    #如果不是标题，当作正文，追加到当前章节的内容

            if current_section["content"].strip():
                sections.append(PaperSection(title=current_section["title"], content=current_section["content"].strip()))
            #把最后一个章节加进去

            #返回结构化内容
            return PdfContent(
                sections=sections,
                figures=[],
                tables=[],
                raw_text=doc.export_to_text(),
                references=[],
                parser_used=ParserType.DOCLING,
                metadata={"source": "docling", "note": "Content extracted from PDF, metadata comes from arXiv API"},
            )

        except PDFValidationError as e:
            error_msg = str(e).lower()
            if "too large" in error_msg or "too many pages" in error_msg:
                logger.info(f"Skipping PDF processing due to size/page limits: {e}")
                return None
            else:
                raise
        except Exception as e:
            logger.error(f"Failed to parse PDF with Docling: {e}")
            logger.error(f"PDF path: {pdf_path}")
            logger.error(f"PDF size: {pdf_path.stat().st_size} bytes")
            logger.error(f"Error type: {type(e).__name__}")

            error_msg = str(e).lower()

            if "not valid" in error_msg:
                logger.error("PDF appears to be corrupted or not a valid PDF file")
                raise PDFParsingException(f"PDF appears to be corrupted or invalid: {pdf_path}")
            elif "timeout" in error_msg:
                logger.error("PDF processing timed out - file may be too complex")
                raise PDFParsingException(f"PDF processing timed out: {pdf_path}")
            elif "memory" in error_msg or "ram" in error_msg:
                logger.error("Out of memory - PDF may be too large or complex")
                raise PDFParsingException(f"Out of memory processing PDF: {pdf_path}")
            elif "max_num_pages" in error_msg or "page" in error_msg:
                logger.error(f"PDF processing issue likely related to page limits (current limit: {self.max_pages} pages)")
                raise PDFParsingException(
                    f"PDF processing failed, possibly due to page limit ({self.max_pages} pages). Error: {e}"
                )
            else:
                raise PDFParsingException(f"Failed to parse PDF with Docling: {e}")
