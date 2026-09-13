'''
HybridIndexingService把论文变成可检索的向量数据，存入Opensearch
1.index_paper单篇论文完整入库
    TextChunker.chunk_paper论文分块
    BGE 本地嵌入模型生成向量
    OpenSearch 批量写入
2.index_papers_batch批量论文入库
    循环调用 index_paper
3.reindex_paper论文更新重索引
    delete删除旧数据
    调用 index_paper
'''
import logging
from typing import Dict, List, Optional

from src.services.embeddings import EmbeddingsClient
from src.services.opensearch.client import OpenSearchClient

from .text_chunker import TextChunker

logger = logging.getLogger(__name__)


#
class HybridIndexingService:
    def __init__(self, chunker: TextChunker, embeddings_client: EmbeddingsClient, opensearch_client: OpenSearchClient):
        self.chunker = chunker
        self.embeddings_client = embeddings_client
        self.opensearch_client = opensearch_client

        logger.info("Hybrid indexing service initialized")

    #用TextChunker将论文分块，调用 BGE 嵌入模型生成向量，
    # 然后做块+向量+论文元数据的映射，最后批量写入Opensearch
    async def index_paper(self, paper_data: Dict) -> Dict[str, int]:
        arxiv_id = paper_data.get("arxiv_id")
        paper_id = str(paper_data.get("id", ""))

        if not arxiv_id:
            logger.error("Paper missing arxiv_id")
            return {"chunks_created": 0, "chunks_indexed": 0, "embeddings_generated": 0, "errors": 1}

        try:
            chunks = self.chunker.chunk_paper(
                title=paper_data.get("title", ""),
                abstract=paper_data.get("abstract", ""),
                full_text=paper_data.get("raw_text", paper_data.get("full_text", "")),
                arxiv_id=arxiv_id,
                paper_id=paper_id,
                sections=paper_data.get("sections"),
            )

            if not chunks:
                logger.warning(f"No chunks created for paper {arxiv_id}")
                return {"chunks_created": 0, "chunks_indexed": 0, "embeddings_generated": 0, "errors": 0}

            logger.info(f"Created {len(chunks)} chunks for paper {arxiv_id}")

            chunk_texts = [chunk.text for chunk in chunks]
            embeddings = await self.embeddings_client.embed_passages(
                texts=chunk_texts,
                batch_size=50,
            )
            #调用向量化客户端，把每一段文本都变成向量

            if len(embeddings) != len(chunks):
                logger.error(f"Embedding count mismatch: {len(embeddings)} != {len(chunks)}")
                return {"chunks_created": len(chunks), "chunks_indexed": 0, "embeddings_generated": len(embeddings), "errors": 1}

            chunks_with_embeddings = []

            for chunk, embedding in zip(chunks, embeddings):
                chunk_data = {
                    "arxiv_id": chunk.arxiv_id,
                    "paper_id": chunk.paper_id,
                    "chunk_index": chunk.metadata.chunk_index,
                    "chunk_text": chunk.text,
                    "chunk_word_count": chunk.metadata.word_count,
                    "start_char": chunk.metadata.start_char,
                    "end_char": chunk.metadata.end_char,
                    "section_title": chunk.metadata.section_title,
                    "embedding_model": self.embeddings_client.model_name,
                    "title": paper_data.get("title", ""),
                    "authors": ", ".join(paper_data.get("authors", []))
                    if isinstance(paper_data.get("authors"), list)
                    else paper_data.get("authors", ""),
                    "abstract": paper_data.get("abstract", ""),
                    "categories": paper_data.get("categories", []),
                    "published_date": paper_data.get("published_date"),
                }

                chunks_with_embeddings.append({"chunk_data": chunk_data, "embedding": embedding})

            results = self.opensearch_client.bulk_index_chunks(chunks_with_embeddings)
            #写入opensearch

            logger.info(f"Indexed paper {arxiv_id}: {results['success']} chunks successful, {results['failed']} failed")

            return {
                "chunks_created": len(chunks),
                "chunks_indexed": results["success"],
                "embeddings_generated": len(embeddings),
                "errors": results["failed"],
            }

        except Exception as e:
            logger.error(f"Error indexing paper {arxiv_id}: {e}")
            return {"chunks_created": 0, "chunks_indexed": 0, "embeddings_generated": 0, "errors": 1}

    #一次性传入多篇论文，循环调用上面的index_paper，然后做一个统计，合成一份总报告
    #然后批量入库
    async def index_papers_batch(self, papers: List[Dict], replace_existing: bool = False) -> Dict[str, int]:
        total_stats = {
            "papers_processed": 0,
            "total_chunks_created": 0,
            "total_chunks_indexed": 0,
            "total_embeddings_generated": 0,
            "total_errors": 0,
        }

        for paper in papers:
            arxiv_id = paper.get("arxiv_id")

            if replace_existing and arxiv_id:
                self.opensearch_client.delete_paper_chunks(arxiv_id)

            stats = await self.index_paper(paper)

            total_stats["papers_processed"] += 1
            total_stats["total_chunks_created"] += stats["chunks_created"]
            total_stats["total_chunks_indexed"] += stats["chunks_indexed"]
            total_stats["total_embeddings_generated"] += stats["embeddings_generated"]
            total_stats["total_errors"] += stats["errors"]

        logger.info(
            f"Batch indexing complete: {total_stats['papers_processed']} papers, "
            f"{total_stats['total_chunks_indexed']} chunks indexed"
        )

        return total_stats

    #先删除论文旧的索引数据，再执行index_paper，重新执行分块、向量化、入库
    async def reindex_paper(self, arxiv_id: str, paper_data: Dict) -> Dict[str, int]:
        deleted = self.opensearch_client.delete_paper_chunks(arxiv_id)
        if deleted:
            logger.info(f"Deleted existing chunks for paper {arxiv_id}")

        return await self.index_paper(paper_data)