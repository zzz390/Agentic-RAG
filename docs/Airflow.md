Airflow负责离线调度、批量处理，能定时拉论文、解析、写PG、建opensearch索引，在docker容器的airflow里跑
Fast API主要负责在线服务，接待用户，用户随时发HTTP请求，用已有索引检索+调ollama答题，在docker的API容器里面跑

Airflow就是按照已经画好的流程图，在指定时间自动跑一串任务，并且记录日志。整个DAG文件就是一个流程图，调度器在容器里面，然后每个Task（setup、fetch等）是工人，src/是业务代码。

## Arxiv_client

客户端进行多种查询：基础查询、按ID查询、高级查询，拼好查询发送get请求，拿到HTTP响应体，里面包含XML字符串，然后把字符串解析成XML树，对XML的每条entry都解析出标题、作者、PDF链接等，组装成Arxivpaper，可以通过PDF链接下载整篇论文。

## PDF_parser

异步处理，对下载的PDF先打上处理标签，然后对PDF做安检，然后把PDF变成结构化数据。

## BGE 本地嵌入

创建 `BGEEmbeddingsClient`，从本地 `models/bge-small-zh-v1.5` 加载 sentence-transformers 模型（**512 维**）。`embed_passages` 批量将 chunk 向量化；`embed_query` 对用户问题向量化（带 BGE 检索前缀）。无需外网 API Key。

## Opensearch_client

创建一个OpenSearchClient，主要有两个功能，一个是把已经结构化后的数据写入opensearch的数据
一个是根据用户问题对库里的内容进行检索，然后返回chunks供大模型使用。
这里主要用写入数据的功能。提供：数据写入（单条写入、批量写入）、数据删除、数据查询
注意：opensearch的使用也要发送HTTP请求，项目用的是官方python客户端，装在容器的依赖包里，会远程调用，完成任务，chunks在这里写入opensearch本质上是写入跑opensearch这个容器所管理的磁盘上。

## Text_chunker

从上到下的逻辑:一篇论文进来，如果有很多章节，就先清洗章节数据，把一些没用的章节去掉，如果没有章节就直接下一步，下一步就是用词工具先处理标点符号（用\S+），然后用滑动窗口滑过整个文章，滑到每个章节就分别对小中大三种长度的章节进行合并、保留、切块处理之后再分成chunk，处理完之后再恢复标点符号，最后存到chunks列表里面

## Hybird_indexer

创建一个HybridIndexingService
对论文批量进行：调用 Text_chunker 把论文切成 chunks，然后调用 **BGE** 对 chunks 列表进行 embedding（512 维），然后把数据写入 opensearch 里面。

## MetadataFetcher

首先调用Arxiv客户端拉取一批论文，组装成Arxivpaper。然后通过PDF链接，把PDF落到本地，然后用PDF parser解析为结构化数据，把结果包成parsedPaper。如果开启了数据库会话，就把parsedPaper和论文元数据upsert写进PG的papers表。

## 组合成整个Arxiv-ingestion

1.Setup，检查opensearch、PostgreSQL，拿到数据库、opensearch、Arxiv客户端，打日志。
2.Fetching，把某一天的论文拉取出来、下载、解析、入库，加上date，打包成一个fetch_results（拉了多少篇、存了多少篇等）推给后面的index任务用。
3.Indexing，从上游任务拿到fetch_results，然后开数据库会话查papers表，然后取最近存入的N篇论文，然后执行切块、向量化、写opensearch。
   在这里，fetch把论文写到PG里面，然后index从PG里面读出来然后切块、向量化、写入opensearch
4.Reporting，从上游取数据，然后拼报告主体report，再查当前全局状态，最后打印整份json报告。
