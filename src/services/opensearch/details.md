## QueryBuilder

- 你给他搜索词、分页、分类、是否最新、是否搜片段，
- 它就给你拼成一个能直接发给Opensearch的完整查询
- init：如果你要搜片段，则优先去正文搜，要是你要搜论文，则优先搜标题
- 总入口build()包含所有查询组件，
- 1._build_query()
  - _build_text_query()文本搜索：根据用户输入的搜索串，拼出OpenSearch里用于「全文匹配」的那一段查询子句
  - _build_filters()分类过滤：如果输入了category类别，就生成过滤条件，筛选出符合要求的文档
- 2._build_source_fields()控制返回字段：看你要搜chunk还是搜论文
- 3._build_highlight()给找到的关键词highlight，加上一个颜色
- 4._build_sort()结果排序：如果输入了搜索词，不按时间排序按相关性排序，如果没输入，按时间排序

## index_config_hybrid

- 是一个建表的模板，程序创建索引的时候会按照这个要求建表
- ARXIV_PAPERS_CHUNKS_MAPPING：mapping解决数据长什么样、怎么搜的问题，要把chunk正文存进去，方便用传统关键词搜索（BM25），同时要把embedding向量也存进去，方便用向量进行语义搜索。
- HYBRID_RRF_PIPELINE：pipeline解决两路结果怎么合成一路的问题，一路按照关键词选出一批候选，一路按照向量相似度再选出一批候选，两路结果交给opensearch用一套固定规则把两路的排名融合成最终排序，这样返回给用户的就是综合了关键词+语义的结果。
- RRF（Reciprocal Rank Fusion，倒数排名融合） 做的是：不看两路原始的 _score 是多少，只看每条文档在各自列表里的名次，再算一个新分数用来排序。
- RRF=Σ1/(k+rank)，排名越靠前（rank 小），1/(k+rank)越大，同一条文档若在两路都靠前，两项加起来就更高，所以会排到更前。

## Client

- 创建一个OpenSearchClient
- 在这里它拿到已经结构化好的、要进入opensearch的数据，按照mapping和pipe，配置创建 chunk 索引与 RRF 流水线，执行写入/批量写入/删除/按论文查询，执行 BM25、向量、混合搜索并返回片段。
- 在这里面对两个不同的选择：
- 拿到上游的chunk，此时就做一个写入opensearch的工作
- 拿到的是用户问题字符串，这个时候就会拼search然后查询之后返回top_k个chunks
- 健康检查：health_check，先检查是否能连上Opensearch、get_index_stats查看索引里有多少数据
- 数据检索：
- _create_hybrid_index在opensearch里确保混合检索用的chunk索引存在，没有就按配置建一个。如果要求强制重建且这个索引存在，就先删掉旧索引再重建。
- 重建或者初次建的时候调用ARXIV_PAPERS_CHUNKS_MAPPING，以这个为模板创建。
- _create_rrf_pipeline在OpenSearch集群里登记一条混合检索用的Search Pipeline同样的要是要重建就调用HYBRID_RRF_PIPELINE重建
- setup_indices(force=True/False)系统初始化，这里设置force确定是否要重建，然后调用_create_hybrid_index和_create_rrf_pipeline，在这里能确定检索用的chunk索引都存在，以及确定后续用的结果融合器的创建
- _search_bm25_only调用QueryBuilder，只用BM25关键词搜索
- search_chunks_vector只用向量进行语义搜索
- _search_hybrid_native调用QueryBuilder，混合搜索
- search_chunks_hybrid调用_search_hybrid_native，做一个混合搜索的对外接口
- search_papers调用_search_bm25_only
- search_unified调用_search_bm25_only、_search_hybrid_native做对外的统一搜索入口
- 第一层：三个干活的核心
- _search_bm25_only、_search_hybrid_native、search_chunks_vector
- 第二层：对外接口
- search_unified每次只会走其中一条路，没有向量或者关了混合，就只走BM25，有向量且开混合就走hybird
- search_chunks_hybrid专门用来混合搜索
- search_papers专门用来做BM25搜索
- search_chunks_vector纯向量对外接口
- 数据写入：index_chunk单条写入，bulk_index_chunks批量写入
- 数据删除：delete_paper_chunks按论文ID删除所有分块
- 数据查询：get_chunks_by_paper按论文ID获取所有分块
- 要注意的点：opensearch的使用也是要发送HTTP请求，项目里用的是 opensearchpy，这是 OpenSearch 的官方 Python 客户端，装在你容器里的依赖包，它会远程调用，完成任务。然后chunks在这里写入opensearch本质上是写入跑opensearch的这个容器所管理的磁盘上。

## Factory

- 创建并返回一个Opensearch client，并且全局只创建一个，全局复用一个链接。
