## Client

### 最底层：

- pdf_cache_dir保证本地PDF缓存目录存在并返回路径
- base_url、namespaces、以及若干与超时、条数、分类、限速相关的 property：把配置读出来给本类其它方法用。

### 第一层：XML单字段读取

这些方法都只处理 「当前这一条 entry 节点」 上的一小块信息：

- _get_text：按带命名空间的路径找到子节点，取出文本；可按需把换行收成空格。
- XML是什么：XML（可扩展标记语言）是一种用标签嵌套表示数据的文本格式，和 HTML 很像：有 <entry>...</entry>、<title>...</title> 这类成对标签，可以表达树状结构（文档 → 章节 → 字段）。
- 然后XML是通用外壳，内部还有Atom、RSS、SOAP（信封、业务体）、SVG （矢量图）等在不同领域上定义的主流「词表/标准」。
- arXiv 返回的是 Atom 格式的 XML，里面的标签都带 XML 命名空间
- 子标签/子元素是什么：XML 是树：大标签套小标签。
- 对 arXiv 来说，一篇论文在 XML 里通常包在一个 <atom:entry>...</atom:entry> 里，这叫一条 entry。
- 子元素就是 直接包在 entry 里面的那些小标签，例如「标题」「摘要」「发布时间」「作者」「链接」等，每个都是 entry的一个子节点。
- namespaces 字典里具体是什么：是键值对
- 键：atom，值（URI）：http://www.w3.org/2005/Atom等等。
- 告诉 ElementTree：当你看到路径里的 atom:title时，要去匹配文档里 属于 http://www.w3.org/2005/Atom 这个命名空间 的 title 元素。
- XML 文件里可能写成带前缀的 atom:title，也可能在内部用「花括号 URI」表示；字典就是把前缀和 URI 对上号，否则 find 经常匹配不到。
- .text 是什么：在 ElementTree 里，某个元素的 .text 一般指：这个标签开头、到第一个子标签之前的那段纯文本
- 在这里就是指title这个子标签到下个子标签之间的内容，其实就是取出标题。
- 也就是说_get_text做的是：一篇论文在XML里包在一个 <atom:entry>...</atom:entry> 里，然后element.find("atom:title", self.namespaces) ，然后根据namespaces的路径定位到这个atom，根据atom:title去找到title，然后取出title这个子标签到下一个子标签之间的内容，也就是取出标题。同理也可以取出摘要、日期等内容
- _get_arxiv_id：从「论文 ID 那条链接」里抽出 短 arXiv 编号；没有则视为无效条目。
- _get_authors：遍历作者节点，拼出作者名字列表。
- _get_categories：遍历分类节点，收集分类代号列表。
- _get_pdf_url：在若干链接里找到 PDF 那条，并把链接规范成安全可用的形式。

### 第 2 层：把一条 entry 变成一篇 ArxivPaper

- _parse_single_entry：对 一篇 Atom entry，依次调用上面的 _get_arxiv_id、_get_text、_get_authors、_get_categories、_get_pdf_url，组装成 一条对外的ArxivPaper；缺关键信息或解析异常则返回「没有这篇」。

### 第 3 层：整段 XML → 多篇论文列表

- _parse_response：把接口返回的 整段 XML 字符串 解析成树，找出所有 entry，对每一个调用 
- xml_data：httpx 拿到的 整段响应文本（字符串），内容是 Atom/XML。
- ET.fromstring(...)：用 xml.etree.ElementTree 把它 解析成一棵 DOM 树。
- DOM：Document Object Model，把 HTML/XML 想成 很多节点搭成的树，每个节点有 标签名、属性、子节点、文本内容，可以用程序 从上往下走、按路径找。
- root：树的根节点，下面挂着很多论文，每个论文都被 entry 包起来，每个 entry 再挂着 title、summary、author、link 等。
- root.findall就是往下一篇一篇取出论文，然后调用_parse_single_entry根据论文内容装成一个个ArxivPaper。

### 第 4 层：对外「拉元数据」入口（HTTP + 解析）

这三者平行，都是 「请求 arXiv → 得到 XML → 调 _parse_response」，差别在 怎么拼查询：

- fetch_papers：用配置里的论文分类、日期区间拼好查询参数，做简单限速，发 GET；→ _parse_response → 返回论文列表。失败区分超时、HTTP 错误等并转成项目自定义异常。
- fetch_papers_with_query：查询串 完全由调用方给（高级检索）；同样限速、GET、→ _parse_response。
- fetch_paper_by_id：用 论文 ID 列表接口 只拉一篇的量；GET、→ _parse_response；有结果则 取第一篇，否则返回空。

### 第 5 层：PDF 下载（与「拉元数据」并列的另一条能力）

- _get_pdf_path：根据论文 ID 生成 缓存目录下的本地文件名路径。
- _download_with_retry：按 URL 流式下载到目标路径，带 重试与退避；多次失败会抛下载相关异常；必要时清理不完整文件。
- download_pdf：输入已是 ArxivPaper（里要带 PDF 链接）；若本地已有文件且不要求强制重下，则 直接返回缓存路径；否则 → _get_pdf_path，再 → _download_with_retry，成功则返回本地路径。

### 全流程：

- 首先用户进行多种查询：基础、按id查、高级查询，然后拼好查询发送get请求，拿到HTTP响应体（XML字符串），把字符串解析成XML树，找出所有entry，对每一条entry都读出标题、作者、PDF链接等，组装成ArxivPaper。如果还要正文，可以用ArxivPaper里面的PDF链接下载
- ArxivClient 一般不是「根据用户聊天里的自然语言问题」去拉论文。

## factory

- 加上配置把Arxivclient做一个对外接口
