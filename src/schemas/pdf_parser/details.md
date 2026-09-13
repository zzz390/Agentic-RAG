## ParserType

• 作用： 标明用哪种解析器抽 PDF；当前只有 DOCLING。
Docling不是系统自带的，是独立安装的第三方库，用来把PDF读成结构化内容。
• 用途： 写进 PdfContent.parser_used，方便日志、排查、以后扩展别的解析器。

## PaperSection

• 作用： 描述一个章节：标题、正文、层级（第几级标题，如 1=大节）。
• 用途： 结构化正文，给后面 TextChunker 按章节分块 用。

## PaperFigure

• 作用： 描述一张图：说明文字（caption）、图 ID。
• 用途： 记录解析器能抽到的图表信息（当前流水线是否强依赖看 parser 实现）。

## PaperTable

• 作用： 描述一张表：表题说明、表 ID。
• 用途： 与图类似，结构化记录表格。

## PdfContent

• 作用： 一次 PDF 解析的「内容包」：
• 章节列表、图列表、表列表
• 整篇拼接后的纯文本 raw_text
• 参考文献字符串列表
• 用的哪种解析器、解析器附加元数据字典
• 用途： 入库、索引时主要吃 sections + raw_text（以及 references 等视业务而定）。

## ArxivMetadata

• 作用： 和 ArxivPaper 对齐的一层 「来自 arXiv 的元数据」：题目、作者、摘要、编号、分类、日期、PDF 链接。
• 用途： 和 ParsedPaper 拼在一起，表示「这篇在 arXiv 上是谁 + PDF 里抽出了什么」。

## ParsedPaper最终数据结构

作用：把arXiv上这篇论文是谁和PDF里抽出了什么，绑成同一个对象，交给下游一步处理（例如序列化进库、写日志、切块索引）

• arxiv_metadata：arXiv 侧信息（必有）
• pdf_content：PDF 抽出来的内容（可能没有，例如没下 PDF、解析失败）
• 用途： MetadataFetcher 等把 ParsedPaper 转成 PaperCreate 再写 PostgreSQL；索引阶段再从库里读出类似结构去切块。
