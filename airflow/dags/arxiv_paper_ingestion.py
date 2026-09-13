from datetime import datetime, timedelta
import importlib

try:
    DAG = importlib.import_module("airflow").DAG
    BashOperator = importlib.import_module("airflow.operators.bash").BashOperator
    PythonOperator = importlib.import_module("airflow.operators.python").PythonOperator
except Exception:
    class _AirflowImportStub:
        def __init__(self, *_args, **_kwargs):
            raise ImportError("apache-airflow is not installed in the current Python environment.")

    DAG = _AirflowImportStub
    BashOperator = _AirflowImportStub
    PythonOperator = _AirflowImportStub


def _setup_environment():
    from arxiv_ingestion.setup import setup_environment

    return setup_environment()


def _fetch_daily_papers():
    from arxiv_ingestion.fetching import fetch_daily_papers

    return fetch_daily_papers()


def _index_papers_hybrid():
    from arxiv_ingestion.indexing import index_papers_hybrid

    return index_papers_hybrid()


def _generate_daily_report():
    from arxiv_ingestion.reporting import generate_daily_report

    return generate_daily_report()

#设置默认参数
default_args = {
    "owner": "arxiv-curator",
    "depends_on_past": False,
    #不依赖上一次任务执行的结果，不会被上一次任务失败影响
    "start_date": datetime(2025, 8, 8),
    "email_on_failure": False,
    "email_on_retry": False,
    #任务失败的时候是否发邮件、任务重试的时候是否发邮件
    "retries": 2,
    #任务最大重试次数
    "retry_delay": timedelta(minutes=30),
    "catchup": False,
    #是否补跑历史未执行的任务
}

dag = DAG(
    "arxiv_paper_ingestion", #DAG的唯一ID
    default_args=default_args,
    description="arXiv 每日流水线：拉取 → 写入 PostgreSQL → 分块与 BGE 向量化 → OpenSearch 混合索引",
    schedule="0 6 * * 1-5", #Cron表达式，表示UTC时间周一到周五早上六点开始运行
    max_active_runs=1,
    catchup=False,
    tags=["arxiv", "papers", "ingestion", "hybrid-search", "embeddings", "chunks"],
    #给DAG打标签，在Airflow后台可以筛选和分类
)

# 任务定义
setup_task = PythonOperator(
    task_id="setup_environment",
    python_callable=_setup_environment,
    dag=dag,
)

fetch_task = PythonOperator(
    task_id="fetch_daily_papers",
    python_callable=_fetch_daily_papers,
    dag=dag,
)

# 混合检索索引任务（分块 + BGE 向量 + 写入 OpenSearch）
index_hybrid_task = PythonOperator(
    task_id="index_papers_hybrid",
    python_callable=_index_papers_hybrid,
    dag=dag,
)

report_task = PythonOperator(
    task_id="generate_daily_report",
    python_callable=_generate_daily_report,
    dag=dag,
)

cleanup_task = BashOperator(
    task_id="cleanup_temp_files",
    bash_command="""
    echo "正在清理临时文件..."
    # 删除 30 天前的 PDF，控制磁盘占用
    find /tmp -name "*.pdf" -type f -mtime +30 -delete 2>/dev/null || true
    echo "清理完成"
    """,
    dag=dag,
)

# 任务依赖：setup → fetch → hybrid index → report → cleanup
setup_task >> fetch_task >> index_hybrid_task >> report_task >> cleanup_task
