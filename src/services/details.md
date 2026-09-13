## MetadataFetcher

### 最底层：

- __init__把拉元数据、下PDF、解析PDF要用的对象和并发上线、缓存路径存起来

### 第一层：单篇下载+解析+可写库字段

- _download_and_parse_pipeline：调用arxiv客户端把PDF落到本地，失败则返回没下载成功。再用PDF parser解析读本地文件，得到结构化正文，成功则把arxiv上的元数据和解析结果包成parsedPaper。
- _serialize_parsed_content：把ParsedPaper里的PDF部分，变成一坨普通字典（正文、章节列表、参考文献、用的哪种解析器、是否算处理成功、处理时间等），方便和 arXiv 元数据 拼在一起。

### 第二层：多篇并发跑下载+解析，把拉到的列表+解析结果写入PostgreSQL

- _process_pdfs_batch建两个并发上限（下载一道闸，解析一道闸），对列表里的每一篇起一个同样的一部任务，内部都是_download_and_parse_pipeline。
  - asyncio.gather 等全部跑完，再逐个看结果：统计 下了多少、解析成功多少；把 每篇成功的 ParsedPaper放进 「按 arXiv 编号索引的字典」，并把失败信息记进 错误列表。
- _store_papers_to_db用传入的数据库会话建PaperRepository。仍按「拉元数据时的那篇列表」逐篇循环：每篇先拼 「来自 arXiv 的固定字段」；
  - 若这篇在 parsed_papers里有解析结果，就 _serialize_parsed_content 把结构化的论文对象转换成数据库能存的字典格式；
  - 没有则打 「只存元数据、PDF 未处理」 类标记。拼成 PaperCreate，upsert（有则更新、无则插入）。循环结束后 commit 一次；若提交失败则 回滚 并把成功篇数清零。

### 第三层：整条流水线（总入口）

fetch_and_process_papers：
拉列表，arXiv客户端按条数+日期范围拉一批ArxivPaper。
可选处理PDF，若打开开关，则 _process_pdfs_batch，得到 下载/解析统计 和 parsed_papers。
可选存库： 若打开开关且给了 数据库会话，则 _store_papers_to_db，把 元数据 ± 解析结果 写进 papers表；没会话则记一条错误说明。
填 耗时，打日志，返回 结果字典（拉了多少、下多少、解析多少、存多少、错误列表等）。
若 整条流水线 出现未预料的大异常，会记错误并 抛「管道失败」类异常。
