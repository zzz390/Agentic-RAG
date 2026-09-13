## arxiv_paper_ingestion

- 负责定义 DAG 和任务依赖，内部顺序：setup → fetch → index → report → cleanup。

### 整个DAG流程：

#### ① setup_environment

- 用 common.get_cached_services() 拿齐客户端。
- 验 PG、验 OpenSearch；创建/确认 chunk 混合索引 + RRF pipeline。
- 不拉论文、不写业务数据；失败则整趟 DAG 停在这里。


#### ② fetch_daily_papers

- 定 目标日期（多为执行日前一天）。
- MetadataFetcher：arXiv 拉元数据 → 下 PDF → Docling 解析 → upsert 进 PG。
- XCom 传出 fetch_results（拉了几篇、存了几篇、日期等）。
- 不写 OpenSearch。


#### ③ index_papers_hybrid

- XCom 读 fetch_results，从 PG 取论文（优先「本次刚存的 N 篇」，否则近 24 小时兜底）。
- HybridIndexingService：切块 → BGE向量化 → bulk 写入 OpenSearch（同篇会先删旧 chunk）。
- XCom 传出 hybrid_index_stats。


#### ④ generate_daily_report

- 合并 fetch + index 的 XCom，再查 PG 总论文数、OS 文档数/体积。
- 打 JSON 日志，XCom 可存 daily_report。
- 只读、只汇总。


#### ⑤ cleanup_temp_files（在 arxiv_paper_ingestion.py 里，Bash）

- 删除 /tmp 下超过 30 天的 PDF，省磁盘。
