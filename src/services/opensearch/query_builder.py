'''
QueryBuilder这个类就是你给他：搜索词、分页、分类、是否最新、是否搜片段，
它就给你拼成一个能直接发给Opensearch的完整查询
init：如果你要搜片段，则优先去正文搜，要是你要搜论文，则优先搜标题
总入口build()包含所有查询组件，
1._build_query()
  _build_text_query()文本搜索：根据用户输入的搜索串，拼出OpenSearch里用于「全文匹配」的那一段查询子句
  _build_filters()分类过滤：如果输入了category类别，就生成过滤条件，筛选出符合要求的文档
2._build_source_fields()控制返回字段：看你要搜chunk还是搜论文
3._build_highlight()给找到的关键词highlight，加上一个颜色
4._build_sort()结果排序：如果输入了搜索词，不按时间排序按相关性排序，如果没输入，按时间排序
'''

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class QueryBuilder:

    def __init__(
        self,
        query: str,
        size: int = 10,
        from_: int = 0,
        #分页偏移量，代表着从第几条开始返回，from是关键字，所以加一个_
        fields: Optional[List[str]] = None,
        #自定义搜索那些字段
        categories: Optional[List[str]] = None,
        track_total_hits: bool = True,
        #精准命中总数统计
        latest_papers: bool = False,
        search_chunks: bool = False,
    ):

        self.query = query
        self.size = size
        self.from_ = from_
        self.categories = categories
        self.track_total_hits = track_total_hits
        self.latest_papers = latest_papers
        self.search_chunks = search_chunks

        if fields is None:
            if search_chunks:
                self.fields = ["chunk_text^3", "title^2", "abstract^1"]
            #^表示权重，也就是说如果用户输入了chunk，那就按照chunk来搜索
            else:
                self.fields = ["title^3", "abstract^2", "authors^1"]
        else:
            self.fields = fields

    def build(self) -> Dict[str, Any]:
    #把后面零散的配置，打包成一个标准的查询请求
        query_body = {
            "query": self._build_query(),
            "size": self.size,
            "from": self.from_,
            "track_total_hits": self.track_total_hits,
            "_source": self._build_source_fields(),
            "highlight": self._build_highlight(),
        }

        sort = self._build_sort()
        if sort:
            query_body["sort"] = sort

        return query_body

    def _build_query(self) -> Dict[str, Any]:

        must_clauses = []
        #初始化列表，用来放必须满足的匹配条件
        if self.query.strip():
            must_clauses.append(self._build_text_query())
        #把用户的搜索词放到列表里

        filter_clauses = self._build_filters()
        #根据用户传入的categories参数，生成过滤条件
        bool_query = {}

        if must_clauses:
            bool_query["must"] = must_clauses
        else:
            bool_query["must"] = [{"match_all": {}}]

        if filter_clauses:
            bool_query["filter"] = filter_clauses

        return {"bool": bool_query}

    def _build_text_query(self) -> Dict[str, Any]:

        return {
            "multi_match": {
                "query": self.query,
                "fields": self.fields,
                "type": "best_fields",
                "operator": "or",
                "fuzziness": "AUTO",
                "prefix_length": 2,
            }
        }

    def _build_filters(self) -> List[Dict[str, Any]]:
        #如果输入了categories就创建一个filter
        filters = []

        if self.categories:
            filters.append({"terms": {"categories": self.categories}})

        return filters

    def _build_source_fields(self) -> Any:
    #控制 OpenSearch 查询后，只返回哪些字段给前端，不返回哪些字段。
        if self.search_chunks:
            return {"excludes": ["embedding"]}
        else:
            return ["arxiv_id", "title", "authors", "abstract", "categories", "published_date", "pdf_url"]


    def _build_highlight(self) -> Dict[str, Any]:
    #给搜索到的关键词加上highlight
        if self.search_chunks:
            return {
                "fields": {
                    "chunk_text": {
                        "fragment_size": 150,
                        "number_of_fragments": 2,
                        "pre_tags": ["<mark>"],
                        "post_tags": ["</mark>"],
                    },
                    "title": {"fragment_size": 0, "number_of_fragments": 0, "pre_tags": ["<mark>"], "post_tags": ["</mark>"]},
                    "abstract": {
                        "fragment_size": 150,
                        "number_of_fragments": 1,
                        "pre_tags": ["<mark>"],
                        "post_tags": ["</mark>"],
                    },
                },
                "require_field_match": False,
            }
        else:
            return {
                "fields": {
                    "title": {
                        "fragment_size": 0,
                        "number_of_fragments": 0,
                    },
                    "abstract": {
                        "fragment_size": 150,
                        "number_of_fragments": 3,
                        "pre_tags": ["<mark>"],
                        "post_tags": ["</mark>"],
                    },
                    "authors": {
                        "fragment_size": 0,
                        "number_of_fragments": 0,
                        "pre_tags": ["<mark>"],
                        "post_tags": ["</mark>"],
                    },
                },
                "require_field_match": False,
            }

    def _build_sort(self) -> Optional[List[Dict[str, Any]]]:
    #如果用户要最新的论文，就按发布时间排序。
    #如果用户输入了搜索词，就不排序，让它自动排序即可
        if self.latest_papers:
            return [{"published_date": {"order": "desc"}}, "_score"]

        if self.query.strip():
            return None

        return [{"published_date": {"order": "desc"}}, "_score"]
