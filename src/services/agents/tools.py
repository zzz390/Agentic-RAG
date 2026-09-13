import logging

from langchain_core.documents import Document
from langchain_core.tools import tool

from src.services.embeddings import EmbeddingsClient
from src.services.opensearch.client import OpenSearchClient
from src.utils.document_sources import paper_source_url

logger = logging.getLogger(__name__)

#它用来创建一个「论文检索工具」，让 AI 智能体可以调用它去查 arXiv 论文。
#LangChain 工具（Tool），智能体看到问题需要查资料时，就会自动调用它。
def create_retriever_tool(
    opensearch_client: OpenSearchClient,
    embeddings_client: EmbeddingsClient,
    top_k: int = 3,
    use_hybrid: bool = True,
):#作用：创建并返回一个可被智能体调用的 “论文检索工具”

    @tool #@tool 是 LangChain 提供的装饰器，它的作用是把一个普通 Python 函数变成一个"AI 智能体可以调用的工具"
    async def retrieve_papers(query: str) -> list[Document]:
        """
        搜索并返回相关的 arXiv 学术论文。
        当用户询问以下内容时，使用这个工具：
        - 机器学习相关概念与技术
        - 深度学习模型与架构
        - 自然语言处理方法
        - 计算机视觉技术
        - 人工智能研究内容
        - 具体算法、模型、论文

        query: 搜索用的查询语句
        返回: 相关的论文片段和元数据
        """
        logger.info(f"Retrieving papers for query: {query[:100]}...")
        logger.debug(f"Search mode: {'hybrid' if use_hybrid else 'bm25'}, top_k: {top_k}")

        query_embedding = None
        search_mode = "bm25"
        if use_hybrid:
            logger.debug("正在生成查询向量")
            try:
                query_embedding = await embeddings_client.embed_query(query)
                search_mode = "hybrid"
                logger.debug("向量维度: %s", len(query_embedding))
            except Exception as exc:
                logger.warning("向量生成失败，降级为 BM25 检索: %s", exc)

        effective_hybrid = use_hybrid and query_embedding is not None

        logger.debug("正在检索 OpenSearch（模式=%s）", search_mode)
        search_results = opensearch_client.search_unified(
            query=query,
            query_embedding=query_embedding,
            size=top_k,
            use_hybrid=effective_hybrid,
        )

        documents = []
        hits = search_results.get("hits", [])
        logger.info(f"Found {len(hits)} documents from OpenSearch")

        for hit in hits:
            doc = Document(
                page_content=hit["chunk_text"],
                metadata={
                    "arxiv_id": hit["arxiv_id"],
                    "title": hit.get("title", ""),
                    "authors": hit.get("authors", ""),
                    "score": hit.get("score", 0.0),
                    "source": paper_source_url(hit.get("arxiv_id", "")),
                    "section": hit.get("section_name", ""),
                    "search_mode": search_mode,
                    "top_k": top_k,
                },
            )
            documents.append(doc)

        logger.debug(f"Converted {len(documents)} hits to LangChain Documents")
        logger.info(f"✓ Retrieved {len(documents)} papers successfully")

        return documents

    return retrieve_papers
