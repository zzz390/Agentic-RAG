import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from src.config import UploadSettings
from src.exceptions import UploadFileTooLargeError, UploadValidationError
from src.models.paper import Paper
from src.repositories.paper import PaperRepository
from src.schemas.arxiv.paper import PaperCreate
from src.services.indexing.hybrid_indexer import HybridIndexingService

from .models import ParsedUploadDocument, UploadIngestResult, UploadIngestStatus
from .service import UploadDocumentService

logger = logging.getLogger(__name__)


class DocumentUploadIngestService:
    """将上传文件保存到 PostgreSQL，并将 chunk 索引到 OpenSearch。"""

    def __init__(
        self,
        upload_parser: UploadDocumentService,
        upload_settings: UploadSettings,
        indexing_service: HybridIndexingService,
    ):
        self.upload_parser = upload_parser
        self.settings = upload_settings
        self.indexing_service = indexing_service

    async def ingest_upload(
        self,
        session: Session,
        file_bytes: bytes,
        original_filename: str,
        title: Optional[str] = None,
    ) -> UploadIngestResult:
        if not original_filename or not original_filename.strip():
            raise UploadValidationError("Uploaded file must have a filename")

        extension = Path(original_filename).suffix.lower()
        if extension not in self.settings.allowed_extension_set():
            allowed = ", ".join(sorted(self.settings.allowed_extension_set()))
            raise UploadValidationError(
                f"Unsupported file type '{extension}'. Allowed extensions: {allowed}"
            )

        size_mb = len(file_bytes) / (1024 * 1024)
        if size_mb > self.settings.max_file_size_mb:
            raise UploadFileTooLargeError(
                f"File size {size_mb:.2f}MB exceeds limit of {self.settings.max_file_size_mb}MB"
            )

        document_id = uuid4()
        arxiv_id = f"upload-{document_id}"
        saved_path = self._save_upload_file(document_id, extension, file_bytes)

        try:
            parsed = await self.upload_parser.parse_file(
                file_path=saved_path,
                original_filename=original_filename,
                title_hint=title,
            )
            paper = self._persist_paper(session, document_id, arxiv_id, parsed, saved_path, title)
            index_stats = await self.indexing_service.index_paper(self._paper_to_index_dict(paper))

            status, message = self._resolve_status(index_stats, parsed.parser_used.value)
            logger.info(
                "Upload ingest complete for %s: status=%s chunks_indexed=%s",
                arxiv_id,
                status,
                index_stats.get("chunks_indexed", 0),
            )

            return UploadIngestResult(
                document_id=document_id,
                arxiv_id=arxiv_id,
                title=paper.title,
                chunks_created=index_stats.get("chunks_created", 0),
                chunks_indexed=index_stats.get("chunks_indexed", 0),
                embeddings_generated=index_stats.get("embeddings_generated", 0),
                parser_used=parsed.parser_used.value,
                status=status,
                message=message,
                original_filename=original_filename,
            )
        except Exception:
            self._cleanup_saved_file(saved_path)
            raise

    def _save_upload_file(self, document_id: UUID, extension: str, file_bytes: bytes) -> Path:
        upload_root = self.settings.resolved_upload_dir()
        document_dir = upload_root / str(document_id)
        document_dir.mkdir(parents=True, exist_ok=True)
        saved_path = document_dir / f"original{extension}"
        saved_path.write_bytes(file_bytes)
        return saved_path

    def _cleanup_saved_file(self, saved_path: Path) -> None:
        try:
            if saved_path.exists():
                saved_path.unlink()
            parent = saved_path.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception as exc:
            logger.warning("Failed to cleanup uploaded file %s: %s", saved_path, exc)

    def _build_abstract(self, raw_text: str) -> str:
        cleaned = raw_text.strip()
        if len(cleaned) <= 500:
            return cleaned
        return f"{cleaned[:500]}..."

    def _persist_paper(
        self,
        session: Session,
        document_id: UUID,
        arxiv_id: str,
        parsed: ParsedUploadDocument,
        saved_path: Path,
        title: Optional[str],
    ) -> Paper:
        now = datetime.now(timezone.utc)
        resolved_title = (title or parsed.title_hint or parsed.original_filename).strip()
        parser_metadata = {
            **parsed.metadata,
            "source_type": "upload",
            "document_id": str(document_id),
            "original_filename": parsed.original_filename,
            "stored_path": str(saved_path),
        }

        paper_create = PaperCreate(
            arxiv_id=arxiv_id,
            title=resolved_title,
            authors=["Unknown"],
            abstract=self._build_abstract(parsed.raw_text),
            categories=["upload"],
            published_date=now,
            pdf_url=f"upload://{arxiv_id}",
            raw_text=parsed.raw_text,
            sections=parsed.sections,
            references=None,
            parser_used=parsed.parser_used.value,
            parser_metadata=parser_metadata,
            pdf_processed=True,
            pdf_processing_date=now,
        )

        paper_repo = PaperRepository(session)
        return paper_repo.create(paper_create)

    def _paper_to_index_dict(self, paper: Paper) -> dict:
        return {
            "id": paper.id,
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "categories": paper.categories,
            "published_date": paper.published_date,
            "raw_text": paper.raw_text,
            "sections": paper.sections,
        }

    def _resolve_status(self, index_stats: dict, parser_used: str) -> tuple[UploadIngestStatus, Optional[str]]:
        chunks_created = index_stats.get("chunks_created", 0)
        chunks_indexed = index_stats.get("chunks_indexed", 0)
        errors = index_stats.get("errors", 0)

        if chunks_created == 0:
            return (
                UploadIngestStatus.FAILED,
                "Document was saved but no searchable chunks were created. The extracted text may be too short.",
            )

        if chunks_indexed == 0 or errors:
            return (
                UploadIngestStatus.PARTIAL,
                "Document was saved to PostgreSQL, but OpenSearch indexing did not complete successfully.",
            )

        return UploadIngestStatus.INDEXED, f"Document indexed successfully using parser '{parser_used}'."
