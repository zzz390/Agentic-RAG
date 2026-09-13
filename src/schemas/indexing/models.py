from typing import Optional

from pydantic import BaseModel

#存储文本块的元信息
class ChunkMetadata(BaseModel):
    chunk_index: int
    start_char: int
    end_char: int
    word_count: int
    overlap_with_previous: int
    overlap_with_next: int
    section_title: Optional[str] = None

#存储完整的文本块数据
class TextChunk(BaseModel):
    text: str
    metadata: ChunkMetadata
    arxiv_id: str
    paper_id: str
