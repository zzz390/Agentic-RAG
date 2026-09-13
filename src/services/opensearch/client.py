'''
1.health_check检查是否能连上Opensearch、get_index_stats查看索引里有多少数据
2.setup_indices(force=True/False)系统初始化
    调用 _create_hybrid_index：创建存储论文分块的表（这里调用ARXIV_PAPERS_CHUNKS_MAPPING）
    调用 _create_rrf_pipeline：创建混合搜索结果融合器（这里调用HYBRID_RRF_PIPELINE）
3.搜索：
search_papers调用_search_bm25_only只用BM25搜索（这里调用QueryBuilder）
search_chunks_vector只用向量搜索
search_chunks_hybrid调用_search_hybrid_native执行混合搜索
search_unified调用_search_bm25_only、_search_hybrid_native对外的统一搜索入口
4.数据写入：index_chunk单条写入，bulk_index_chunks批量写入
5.数据删除：delete_paper_chunks按论文ID删除搜友分块
6.数据查询：get_chunks_by_paper按论文ID获取所有分块
'''

import logging
from typing import Any, Dict, List, Optional

from opensearchpy import OpenSearch
from src.config import Settings

from .index_config_hybrid import HYBRID_RRF_PIPELINE, build_hybrid_chunks_mapping
from .query_builder import QueryBuilder

logger = logging.getLogger(__name__)


class OpenSearchClient:

    def __init__(self, host: str, settings: Settings):
        self.host = host
        self.settings = settings
        self.index_name = f"{settings.opensearch.index_name}-{settings.opensearch.chunk_index_suffix}"
        #拼接生成最终的Opensearch索引名称

        self.client = OpenSearch(
            hosts=[host],
            #Opensearch服务的地址
            use_ssl=False,
            #不启用HTTPS加密链接
            verify_certs=False,
            #不验证SSL证书
            ssl_show_warn=False,
            #关闭SSL相关的警告信息
        )

        logger.info(f"OpenSearch client initialized with host: {host}")

    def health_check(self) -> bool:
    #检查健康状态
        try:
            health = self.client.cluster.health()
            return health["status"] in ["green", "yellow"]
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_index_stats(self) -> Dict[str, Any]:
    #获取OpenSearch索引的统计信息（是否存在、多少文档、占用空间…）
        try:
            if not self.client.indices.exists(index=self.index_name):
                return {"index_name": self.index_name, "exists": False, "document_count": 0}
            #判断索引是否存在

            stats_response = self.client.indices.stats(index=self.index_name)
            #调用opensearch API获取索引统计数据
            index_stats = stats_response["indices"][self.index_name]["total"]
            #从返回的大字典取出总统计部分，结构为indices-索引名-total

            return {
                "index_name": self.index_name,
                "exists": True,
                "document_count": index_stats["docs"]["count"],
                "deleted_count": index_stats["docs"]["deleted"],
                "size_in_bytes": index_stats["store"]["size_in_bytes"],
            }

        except Exception as e:
            logger.error(f"Error getting index stats: {e}")
            return {"index_name": self.index_name, "exists": False, "document_count": 0, "error": str(e)}

    def get_index_embedding_dimension(self) -> Optional[int]:
        try:
            if not self.client.indices.exists(index=self.index_name):
                return None
            mapping = self.client.indices.get_mapping(index=self.index_name)
            properties = mapping[self.index_name]["mappings"]["properties"]
            return properties["embedding"]["dimension"]
        except Exception as e:
            logger.warning(f"Could not read embedding dimension for {self.index_name}: {e}")
            return None

    def setup_indices(self, force: bool = False) -> Dict[str, bool]:
    #force表示要不要强制重建，如果为true，就会先删掉旧的再重建
        results = {}
        results["hybrid_index"] = self._create_hybrid_index(force)
        results["rrf_pipeline"] = self._create_rrf_pipeline(force)
        return results

    def _create_hybrid_index(self, force: bool = False) -> bool:
        try:
            if force and self.client.indices.exists(index=self.index_name):
                self.client.indices.delete(index=self.index_name)
                logger.info(f"Deleted existing hybrid index: {self.index_name}")

            if not self.client.indices.exists(index=self.index_name):
                index_body = build_hybrid_chunks_mapping(self.settings.opensearch.vector_dimension)
                self.client.indices.create(index=self.index_name, body=index_body)
                logger.info(
                    f"Created hybrid index: {self.index_name} "
                    f"(embedding dimension={self.settings.opensearch.vector_dimension})"
                )
                return True

            logger.info(f"Hybrid index already exists: {self.index_name}")
            return False

        except Exception as e:
            if "resource_already_exists_exception" in str(e):
                logger.info(f"Hybrid index already exists (created by another worker): {self.index_name}")
                return False
            logger.error(f"Error creating hybrid index: {e}")
            raise

    def _create_rrf_pipeline(self, force: bool = False) -> bool:
        try:
            pipeline_id = HYBRID_RRF_PIPELINE["id"]

            if force:
                try:
                    self.client.ingest.get_pipeline(id=pipeline_id)
                    self.client.ingest.delete_pipeline(id=pipeline_id)
                    logger.info(f"Deleted existing RRF pipeline: {pipeline_id}")
                except Exception:
                    pass

            try:
                self.client.ingest.get_pipeline(id=pipeline_id)
                logger.info(f"RRF pipeline already exists: {pipeline_id}")
                return False
            except Exception:
                pass
            pipeline_body = {
                "description": HYBRID_RRF_PIPELINE["description"],
                "phase_results_processors": HYBRID_RRF_PIPELINE["phase_results_processors"],
            }

            self.client.transport.perform_request("PUT", f"/_search/pipeline/{pipeline_id}", body=pipeline_body)

            logger.info(f"Created RRF search pipeline: {pipeline_id}")
            return True

        except Exception as e:
            logger.error(f"Error creating RRF pipeline: {e}")
            raise

    def search_papers(
        self, query: str, size: int = 10, from_: int = 0, categories: Optional[List[str]] = None, latest: bool = True
    ) -> Dict[str, Any]:
        return self._search_bm25_only(query=query, size=size, from_=from_, categories=categories, latest=latest)

    def search_chunks_vector(
        self, query_embedding: List[float], size: int = 10, categories: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        try:
            filter_clause = []
            if categories:
                filter_clause.append({"terms": {"categories": categories}})

            search_body = {
                "size": size,
                "query": {"knn": {"embedding": {"vector": query_embedding, "k": size}}},
                "_source": {"excludes": ["embedding"]},
            }

            if filter_clause:
                search_body["query"] = {"bool": {"must": [search_body["query"]], "filter": filter_clause}}

            response = self.client.search(index=self.index_name, body=search_body)

            results = {"total": response["hits"]["total"]["value"], "hits": []}

            for hit in response["hits"]["hits"]:
                chunk = hit["_source"]
                chunk["score"] = hit["_score"]
                chunk["chunk_id"] = hit["_id"]
                results["hits"].append(chunk)

            return results

        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return {"total": 0, "hits": []}

    def search_unified(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None,
        size: int = 10,
        from_: int = 0,
        categories: Optional[List[str]] = None,
        latest: bool = False,
        use_hybrid: bool = True,
        min_score: float = 0.0,
    ) -> Dict[str, Any]:

        try:
            if not query_embedding or not use_hybrid:
                return self._search_bm25_only(query=query, size=size, from_=from_, categories=categories, latest=latest)

            return self._search_hybrid_native(
                query=query, query_embedding=query_embedding, size=size, categories=categories, min_score=min_score
            )

        except Exception as e:
            logger.error(f"Unified search error: {e}")
            return {"total": 0, "hits": []}

    #只用BM25关键词检索，从论文分块里查找，并返回格式化结果
    def _search_bm25_only(
        self, query: str, size: int, from_: int, categories: Optional[List[str]], latest: bool
    ) -> Dict[str, Any]:
        builder = QueryBuilder(
            query=query,
            size=size,
            from_=from_,
            categories=categories,
            latest_papers=latest,
            search_chunks=True, #分块查找，chunk_text权重为3，title权重为2，abstract权重为1
        )
        search_body = builder.build()

        response = self.client.search(index=self.index_name, body=search_body)

        results = {"total": response["hits"]["total"]["value"], "hits": []}

        for hit in response["hits"]["hits"]:
            chunk = hit["_source"]
            chunk["score"] = hit["_score"]
            chunk["chunk_id"] = hit["_id"]

            if "highlight" in hit:
                chunk["highlights"] = hit["highlight"]

            results["hits"].append(chunk)

        logger.info(f"BM25 search for '{query[:50]}...' returned {results['total']} results")
        return results

    #用混合检索，BM25关键词+向量语义
    def _search_hybrid_native(
        self, query: str, query_embedding: List[float], size: int, categories: Optional[List[str]], min_score: float
    ) -> Dict[str, Any]:
        builder = QueryBuilder(
            query=query, size=size * 2, from_=0, categories=categories, latest_papers=False, search_chunks=True
        )
        bm25_search_body = builder.build()

        bm25_query = bm25_search_body["query"]

        hybrid_query = {"hybrid": {"queries": [bm25_query, {"knn": {"embedding": {"vector": query_embedding, "k": size * 2}}}]}}

        search_body = {
            "size": size,
            "query": hybrid_query,
            "_source": bm25_search_body["_source"],
            "highlight": bm25_search_body["highlight"],
        }

        response = self.client.search(
            index=self.index_name, body=search_body, params={"search_pipeline": HYBRID_RRF_PIPELINE["id"]}
        )

        results = {"total": response["hits"]["total"]["value"], "hits": []}

        for hit in response["hits"]["hits"]:
            if hit["_score"] < min_score:
                continue

            chunk = hit["_source"]
            chunk["score"] = hit["_score"]
            chunk["chunk_id"] = hit["_id"]

            if "highlight" in hit:
                chunk["highlights"] = hit["highlight"]

            results["hits"].append(chunk)

        results["total"] = len(results["hits"])
        logger.info(f"Native hybrid search for '{query[:50]}...' returned {results['total']} results")
        return results

    #这个函数调用上一个函数_search_hybrid_native，做一个对外的公开接口
    def search_chunks_hybrid(
        self,
        query: str,
        query_embedding: List[float],
        size: int = 10,
        categories: Optional[List[str]] = None,
        min_score: float = 0.0,
    ) -> Dict[str, Any]:
        return self._search_hybrid_native(
            query=query, query_embedding=query_embedding, size=size, categories=categories, min_score=min_score
        )

    #把论文分块+向量写入Opensearch里面，让它能够被搜索到
    def index_chunk(self, chunk_data: Dict[str, Any], embedding: List[float]) -> bool:
        try:
            chunk_data["embedding"] = embedding

            response = self.client.index(index=self.index_name, body=chunk_data, refresh=True)

            return response["result"] in ["created", "updated"]

        except Exception as e:
            logger.error(f"Error indexing chunk: {e}")
            return False

    #批量插入大量论文分块和向量到opensearch里面
    def bulk_index_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, int]:
        from opensearchpy import helpers

        try:
            actions = []
            for chunk in chunks:
                chunk_data = chunk["chunk_data"].copy()
                chunk_data["embedding"] = chunk["embedding"]

                action = {"_index": self.index_name, "_source": chunk_data}
                actions.append(action)

            success, failed = helpers.bulk(self.client, actions, refresh=True)

            logger.info(f"Bulk indexed {success} chunks, {len(failed)} failed")
            return {"success": success, "failed": len(failed)}

        except Exception as e:
            logger.error(f"Bulk chunk indexing error: {e}")
            raise

    #根据论文的ID，一次性删除这篇论文对应的所有分块数据
    def delete_paper_chunks(self, arxiv_id: str) -> bool:
        try:
            response = self.client.delete_by_query(
                index=self.index_name, body={"query": {"term": {"arxiv_id": arxiv_id}}}, refresh=True
            )

            deleted = response.get("deleted", 0)
            logger.info(f"Deleted {deleted} chunks for paper {arxiv_id}")
            return deleted > 0

        except Exception as e:
            logger.error(f"Error deleting chunks: {e}")
            return False

    #查出这篇论文被切成的所有chunks，按顺序返回
    def get_chunks_by_paper(self, arxiv_id: str) -> List[Dict[str, Any]]:
        try:
            search_body = {
                "query": {"term": {"arxiv_id": arxiv_id}},
                "size": 1000,
                "sort": [{"chunk_index": "asc"}],
                "_source": {"excludes": ["embedding"]},
            }

            response = self.client.search(index=self.index_name, body=search_body)

            chunks = []
            for hit in response["hits"]["hits"]:
                chunk = hit["_source"]
                chunk["chunk_id"] = hit["_id"]
                chunks.append(chunk)

            return chunks

        except Exception as e:
            logger.error(f"Error getting chunks: {e}")
            return []
