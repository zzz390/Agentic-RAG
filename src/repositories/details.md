## PaperRepository

### 前置知识：

- PostgreSQL 里的 papers 表：就是硬盘上的一张表，一行 = 一篇论文（编号、标题、作者、摘要、有没有解析过 PDF、正文有没有抽出来等）。
- Paper：就是表里的一行的对象：从库里查出来的就是他，要往表里插也是先做成paper
- PaperCreate：还没进库时，流水线整理好的一包数据（标题、作者、正文、章节等），用 Pydantic 校验格式。也就是一张已经填好的入库申请表
- Session会话：和 PostgreSQL 说话的一条通道：查、插、改，最后 commit 才真正写到磁盘。

### 最底层：基础

- __init__保存一个 SQLAlchemy 数据库会话，后面所有操作都走这个 session。是数据库之间的临时对话通道，增删改查都由它来操作

### 第一层：按一个条件查一行

- get_by_arxiv_id：用arXiv论文编号去表里找，最多一篇，没有就返回空，找到的是表里的一行，也就是一整个paper
- get_by_id：用系统自己发的UUID主键找一篇，没有就返回空

### 第二层：查很多行，数有多少行

- get_all：分页列出论文，按发布顺序新的在前。
- get_count：数表里一共有多少篇论文

### 第三层：按进度处理筛着读

- get_processed_papers：列 已经标记为「PDF 处理过」 的论文，分页
- get_unprocessed_papers：列还没处理PDF的论文、分页
- get_papers_with_raw_text：只列 已经抽出正文（raw_text 有内容）的论文，分页。

### 第四层：把上面几次查询合成一个报表

- get_processing_stats：不算具体列表，只算：总共有多少篇、多少篇PDF已处理、多少篇有正文、处理率，正文提取率。先调get_count，再单独算已处理、有正文

### 第五层：往表里写

- Update：这篇 已经在表里有一行了，你在内存里改过这个 Paper 对象，这里 把改动保存进 PostgreSQL
- Create：新论文第一次入库，表里还没有这篇论文，把 PaperCreate（申请表） 里的字段，填进一个新的 Paper（新档案），插入papers表里面，提交，返回带新id的那一行。
- Upsert：有则更新、无则新建，先get_by_arxiv_id 看表里有没有这篇，有的话就用 paper_create 里的新信息 覆盖 旧行，再 update，没有就走create路线。
