## Text_chunker

整个TextChunker就是把一篇长论文，切成大小合适、上下文完整、
无垃圾内容的小文本，用于后续向量化、存入数据库、RAG检索

### 第一层：词工具

- _split_into_words把输入的text字符串，分隔成一个单词列表
- _reconstruct_text把之前分割好的单词列表重新拼接成完整的文本字符串
- 按照窗口滑动计数的时候会把标点符号也计入，所以先拆开，按照词来计数，拆分之后再合并起来，把标点符号恢复。

### 第二层：无章节假设的滑动窗口

- chunk_text最基础的按单词分块，把文本切成固定大小、带重叠的小块，用于向量检索

### 第三层：章节数据清洗

- _is_metadata_section章节检测器，用来判断一个章节是不是元数据（作者、邮箱等），是的话就过滤掉
- _is_duplicate_abstract内容重复检测器，专门判断章节内容是不是和摘要高度重复，如果是，就判定为重复，后面就过滤掉
- _is_metadata_content垃圾内容检测器，不看标题，只看内容里有没有邮箱、大学等，短文本里出现多个就判定为垃圾文本
- _filter_sections调用_is_metadata_section、_is_duplicate_abstract、_is_metadata_content，把没用的章节（作者、邮箱、重复摘要、元数据）都删掉，只留下正文内容
- _parse_sections章节格式统一器，不管是传入的格式是字典、列表还是JSON字符串，都解析为字典

### 第四层：章节里chunk怎么落地

- _create_section_chunk把已经定好的chunk_text字符串包成一个带元数据的textchunk对象
- _create_combined_chunk把多个小节的正文格式化成「带 Section 标题的合并文本」；若整体很短且有上一块，就合并进上一块省碎片；否则新建一块，调用_create_section_chunk带上章节名说明。
- _split_large_section大章节切割器，当一个章节太长时，先去掉固定表头，用普通chunk_text切成多端，再把表头拼回每一段前面，保证每一块都有完整上下文，并更新元数据，得到一串更适合检索和阅读的chunk。

### 第五层：

- _chunk_by_sections，调用_filter_sections、_is_metadata_content拼公共header（标题+摘要），按节词数：<100走合并逻辑，100-800单块、>800走按大章节拆分，把结果累进chunks列表

### 第六层：对外入口

- chunk_paper有sections则调用_chunk_by_sections，成功且非空就返回，否则就chunk_text(full_text)

也就是说这里从上到下的逻辑就是一篇论文进来，如果有很多章节，就先清洗章节数据，把一些没用的章节去掉，让章节大小适宜，如果没有章节就直接下一步，下一步就是用词工具先处理标点符号（用\S+），然后用滑动窗口滑过整个文章，滑到每个章节就分别对小中大三种长度的章节进行合并、保留、切块处理之后再分成chunk，处理完之后再恢复标点符号，最后存到chunks列表里面

## hybrid_indexer

- 创建一个HybridIndexingService
- index_paper单篇论文从字典到opensearch里有可搜chunk的完整流水线。
- index_paper对已经传入的一篇论文字典调用TextChunker的chunk_paper把拿到的论文进行切块，然后调用 BGE 对这些切块后的 chunks 进行 embedding（512 维），然后再把数据写入 opensearch，然后 index_papers_batch循环调用 index_paper把数据存入 opensearch，然后总结出一个总报告。
- reindex_paper先清空论文在opensearch里的chunk，再重新建索引，避免新旧的chunks混在一起

## factory

- 从环境变量里面取配置，然后按照上面的配置做一个实例化接口
