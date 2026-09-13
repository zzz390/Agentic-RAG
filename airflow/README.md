# Airflow 配置说明

本目录包含 **Apache Airflow** 的镜像构建、入口脚本与 **DAG**，用于 arXiv 论文策展项目的任务编排与定时数据摄入。

<p align="center">
  <img src="../static/week2_data_ingestion_flow.png" alt="第 2 周数据摄入架构" width="800">
</p>

## 当前范围（第 2 周）

下列 DAG 与流水线能力与课程 **第 2 周** 数据摄入阶段一致。

### 生产级 DAG

- **`arxiv_paper_ingestion.py`**：生产主流程——自动拉取并处理 arXiv 论文  

### 流水线能力概览

- **每日 arXiv 摄入**：自动拉取 CS.AI 等类别论文  
- **PDF 处理**：使用 Docling 下载并解析 PDF  
- **数据库存储**：将完整元数据与解析内容写入 PostgreSQL  
- **错误处理**：重试、失败记录与报告  
- **跨平台**：可在 macOS、Linux、WSL、Ubuntu 等环境运行  

## 目录结构

```
airflow/
├── README.md                 # 本说明
├── Dockerfile              # 自定义 Airflow 镜像（含系统与 Python 依赖）
├── requirements-airflow.txt # DAG 运行时 Python 依赖
└── dags/
    ├── arxiv_paper_ingestion.py
    └── arxiv_ingestion/
        └── tasks.py        # 生产流水线任务（含异步处理）
```

若与仓库中实际文件名略有出入，以 **`dags/` 目录下为准**。

## Docker 与镜像

### 跨平台说明

- **用户**：以 `airflow` 用户（UID/GID **50000**）运行，减轻卷权限问题；`compose.yml` 里 WSL/Ubuntu 可对 `user` 另行配置  
- **日志卷**：日志使用命名卷等方式，减少 bind mount 冲突  
- **数据库**：连接项目共用的 **PostgreSQL** 实例  
- **依赖顺序**：配合 Compose 的初始化与健康检查  

### 镜像内能力

- **Python 3.12** + **Apache Airflow 2.10.3**  
- **PostgreSQL**：通过 `psycopg2` 连接  
- **PDF**：Docling、Tesseract OCR、Poppler 等系统工具  
- **合规**：对 arXiv API 做限流与重试  
- **性能**：异步与并发控制，兼顾笔记本等资源受限环境  

## 使用方式

### Web 界面

- **地址**：http://localhost:8080  
- **账号密码**：容器首次初始化时自动生成（见启动日志）  
- **功能**：DAG 状态、任务日志、流水线统计等  

### 生产 DAG（`arxiv_paper_ingestion`）步骤概览

1. **环境**：检查依赖服务并初始化缓存等  
2. **按日拉取**：默认拉取前一日论文（数量可配置，如 10 篇）  
3. **PDF**：下载并用 Docling 解析  
4. **失败重试**：处理解析失败的 PDF  
5. **入库**：完整论文数据与解析内容写入 PostgreSQL  
6. **OpenSearch**：第 3 周前可为占位/预留步骤  
7. **日报**：生成处理统计  

### 性能与策略

- **并发**：例如并行下载与单路解析等（可按机器调整）  
- **限流**：遵守 arXiv 使用规范（如约 3 秒间隔）  
- **缓存**：PDF 落盘缓存，避免重复下载  
- **容错**：单篇失败不阻断整批任务  

## 配置

### 环境变量示例

```bash
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://rag_user:rag_password@postgres:5432/rag_db
AIRFLOW__CORE__EXECUTOR=LocalExecutor
POSTGRES_DATABASE_URL=postgresql+psycopg2://rag_user:rag_password@postgres:5432/rag_db
PYTHONPATH=/opt/airflow/src
```

### 服务依赖

- **PostgreSQL**：论文元数据与内容存储  
- **源码**：将仓库 `src` 挂载到容器内（如 `/opt/airflow/src`），供 DAG 调用业务代码  
- **网络**：与 API、数据库等处于同一 Docker 网络，通过服务名互通  

## 实现状态与后续

### 已完成（课程相关）

- 自定义镜像与依赖安装  
- 生产级 arXiv 摄入 DAG 与错误处理  
- 异步 PDF 流水线及并发控制  
- PostgreSQL 全量存储对接  
- 跨平台运行、API 限流与重试、日志与可观测基础  

### 第 3 周及以后可扩展

- **OpenSearch**：由占位改为真实索引写入  
- **调度策略**：更多采集与调度策略  
- **监控告警**：生产级可观测与告警  
- **扩展性**：提高并发以贴近生产负载  
