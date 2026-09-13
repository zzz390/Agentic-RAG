## common

- 在 Airflow 里统一、缓存地组装 arXiv 客户端、PDF 解析、数据库、MetadataFetcher、OpenSearch 客户端，供 DAG 各任务共用。

## Setup

- 开工检查+把opensearch准备好。
- get_cached_services() 拿到数据库、OpenSearch、arXiv 客户端等。
- 测 PostgreSQL：执行 SELECT 1，确认能连上。
- 测 OpenSearch：看集群健康状态
- opensearch_client.setup_indices(force=False)没有混合索引就 按 mapping 创建，没有 RRF 流水线就 注册，已存在则跳过（force=False 不删重建）
- 打日志：arXiv 地址、PDF 解析服务就绪等。
- 返回 {"status": "success", ...}；任一步失败则 抛异常，Airflow 会把本任务标失败。

## fetching

- 两个函数：一个干实事（异步），一个是 Airflow 任务入口（同步）。
- run_paper_ingestion_pipeline对 某一天 跑完整条「拉论文 → 可选下 PDF/解析 → 存库」流水线。
- fetch_daily_papers：算「要拉哪天的论文」，然后asyncio.run在同步的 Airflow worker里跑run_paper_ingestion_pipeline，然后打日志，
  - 最后整理结果在返回字典里加上date，若有任务实例ti，用XCom把结果以fetch_results为key推给下游任务。return results 给 Airflow。
- ti = Task Instance（任务实例），是 Airflow 里 「这一次 DAG 跑起来时，某一个具体任务」 的句柄。
- XCom = Cross-Communication，Airflow 提供的 「任务之间传小纸条」 的机制。上游任务xcom_push会把结果推给同一DAG里排在后面的任务。
- 意思是：这次 fetch 跑完后，把 results（拉了多少篇、存了多少篇等统计）存起来，标签名叫 fetch_results，给后面的 index 任务用。

## Indexing

- 负责 「从 PostgreSQL 读出论文 → 切块、向量化 → 写入 OpenSearch」，是 fetch 任务之后的 建检索库 环节。
- _index_papers_with_chunks异步，干实事。作用：把 一批论文 交给 HybridIndexingService 做批量索引。
- 一篇一篇论文拿出来，然后处理成格式化数据的字典，放进papers_data列表。
- 全部放进列表之后，最后调用HybridIndexingService做批量索引。
- index_papers_hybrid
- DAG 里 index_papers_hybrid 任务 执行的函数：决定 索引哪些论文，再跑上面的异步索引。
- 首先make_database()，取 ti（任务实例）。读上游的XCom拿到fetch统计。开数据库会话，查paper表，如果上面有拿到fetch_results 且 papers_stored > 0，
  - 就取最近存入的N篇论文，如果没有XCom或者没存成功，就取过去24小时存入的论文。然后执行切块 + 向量 + 写 OpenSearch。
- verify_hybrid_index检查opensearch里混合搜索是否健康，规模如何。
- **在这里，fetch把论文写到PG里面，然后index从PG里面读出来然后切块、向量化、写入opensearch**

## Reporting

- 汇总这一趟流水线跑下来的结果，写日志，可选再给下游留一份 XCom；不改数据、不建索引。
- 取ti，从上游XCom拉统计：fetch_daily_papers → fetch_results（拉了多少、存了多少、目标日期等），index_papers_hybrid → hybrid_index_stats（索引了几篇、多少 chunk、多少向量等）
- 拼报告主体 report。再查「当前全局状态」（实时查库，不只信 XCom）。logger.info 打出整份 JSON 报告。ti.xcom_push留给后面需要用的地方。
