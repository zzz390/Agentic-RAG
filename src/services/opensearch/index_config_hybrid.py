"""
用于混合搜索的 OpenSearch 索引配置（BM25 关键词搜索 + 向量搜索）。
该配置同时支持：
1. 关键词搜索（BM25算法）
2. 向量相似度搜索（使用 HNSW 算法进行近似最近邻查找）
"""

ARXIV_PAPERS_CHUNKS_INDEX = "arxiv-papers-chunks"


def build_hybrid_chunks_mapping(vector_dimension: int) -> dict:
    """根据配置的 knn 向量维度构建 OpenSearch 索引 body。"""
    return _hybrid_chunks_mapping_template(vector_dimension)


def _hybrid_chunks_mapping_template(vector_dimension: int) -> dict:
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index.knn": True,
            "index.knn.space_type": "cosinesimil",
            "analysis": {
                "analyzer": {
                    "standard_analyzer": {"type": "standard", "stopwords": "_english_"},
                    "text_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "stop", "snowball"],
                    },
                }
            },
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "chunk_id": {"type": "keyword"},
                "arxiv_id": {"type": "keyword"},
                "paper_id": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "chunk_text": {
                    "type": "text",
                    "analyzer": "text_analyzer",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                },
                "chunk_word_count": {"type": "integer"},
                "start_char": {"type": "integer"},
                "end_char": {"type": "integer"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": vector_dimension,
                    "method": {
                        "name": "hnsw", # HNSW 算法
                        "space_type": "cosinesimil", #余弦相似度
                        "engine": "nmslib",
                        # HNSW 参数必须放在 parameters 内；method 顶层不接受 m。
                        "parameters": {"ef_construction": 512, "m": 16},
                    },
                },
                "title": {
                    "type": "text",
                    "analyzer": "text_analyzer",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                },
                "authors": {
                    "type": "text",
                    "analyzer": "standard_analyzer",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                },
                "abstract": {"type": "text", "analyzer": "text_analyzer"},
                "categories": {"type": "keyword"},
                "published_date": {"type": "date"},
                "section_title": {"type": "keyword"},
                "embedding_model": {"type": "keyword"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            },
        },
    }


# BGE-small-zh-v1.5 默认 mapping（512 维向量）
ARXIV_PAPERS_CHUNKS_MAPPING = _hybrid_chunks_mapping_template(512)

#把 BM25（关键词）和 KNN（向量）的结果，用 RRF 算法智能融合
HYBRID_RRF_PIPELINE = {
    "id": "hybrid-rrf-pipeline",
    "description": "混合搜索结果后处理流水线（RRF 排序融合）",
    "phase_results_processors": [
        {
            "score-ranker-processor": {
                "combination": {
                    "technique": "rrf",  # 排序倒数融合（自动平衡关键词与向量结果）
                    "rank_constant": 60,  # RRF 公式参数：1/(k+rank)
                }
            }
        }
    ],
}
