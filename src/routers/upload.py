import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from src.dependencies import SessionDep, UploadIngestDep
from src.exceptions import (
    UnsupportedUploadFormatError,
    UploadFileTooLargeError,
    UploadParsingException,
    UploadValidationError,
)
from src.schemas.api.upload import UploadResponse
from src.services.document_upload.models import UploadIngestStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["文档"])


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(
    session: SessionDep,
    ingest_service: UploadIngestDep,
    file: UploadFile = File(..., description="待入库的文档文件"),
    title: Optional[str] = Form(None, description="可选显示标题"),
) -> UploadResponse:
    """
    上传文档：写入 PostgreSQL，并将可检索 chunk 索引到 OpenSearch。

    支持格式：PDF、TXT、Markdown、DOCX、XLSX、XLS。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="上传文件必须包含文件名")

    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=422, detail="上传文件为空")

        result = await ingest_service.ingest_upload(
            session=session,
            file_bytes=file_bytes,
            original_filename=file.filename,
            title=title,
        )

        if result.status == UploadIngestStatus.FAILED:
            raise HTTPException(status_code=422, detail=result.message or "文档入库失败")

        return UploadResponse(
            document_id=result.document_id,
            arxiv_id=result.arxiv_id,
            title=result.title,
            original_filename=result.original_filename,
            chunks_created=result.chunks_created,
            chunks_indexed=result.chunks_indexed,
            embeddings_generated=result.embeddings_generated,
            parser_used=result.parser_used,
            status=result.status.value,
            message=result.message,
        )
    except UnsupportedUploadFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except UploadFileTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UploadParsingException as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected upload error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"上传失败: {exc}") from exc
