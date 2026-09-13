FROM python:3.12-slim

# 环境变量：Airflow 家目录、版本、Python 版本、官方约束文件 URL
ENV AIRFLOW_HOME=/opt/airflow
ENV AIRFLOW_VERSION=2.10.3
ENV PYTHON_VERSION=3.12
ENV CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

# pip 源（网络慢时可构建时覆盖），例如：--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple
# docling/torch 等 NVIDIA 轮子：部分镜像站与 PyPI 哈希不一致；本层默认仍用 pypi.org
ARG PIP_TASK_DEPS_INDEX_URL=https://pypi.org/simple
ENV PIP_DEFAULT_TIMEOUT=600

# 安装系统依赖；国际线路不稳时使用清华 Debian 镜像并重试 apt
RUN if [ -f /etc/apt/sources.list ]; then \
      sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g; s|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list; \
    fi && \
    if [ -d /etc/apt/sources.list.d ]; then \
      find /etc/apt/sources.list.d -type f \( -name "*.list" -o -name "*.sources" \) -exec sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g; s|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' {} +; \
    fi && \
    for i in 1 2 3 4 5; do \
      apt-get update -o Acquire::Retries=8 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 && break; \
      echo "apt-get update failed, retrying ($i/5)..." && sleep 10; \
    done && \
    for i in 1 2 3 4 5; do \
      apt-get install -y --fix-missing --no-install-recommends \
        -o Acquire::Retries=8 \
        -o Acquire::http::Timeout=60 \
        -o Acquire::https::Timeout=60 \
        build-essential \
        curl \
        git \
        libpq-dev \
        poppler-utils \
        tesseract-ocr && break; \
      echo "apt-get install failed, retrying ($i/5)..." && \
      dpkg --configure -a || true && \
      apt-get -f install -y || true && \
      sleep 10; \
    done && \
    rm -rf /var/lib/apt/lists/*

# 创建 airflow 用户，UID/GID 50000，便于跨平台与卷权限一致
RUN groupadd -r -g 50000 airflow && useradd -r -u 50000 -g airflow -d ${AIRFLOW_HOME} -s /bin/bash airflow

# 创建目录并设置属主与权限
RUN mkdir -p ${AIRFLOW_HOME} && \
    mkdir -p ${AIRFLOW_HOME}/dags && \
    mkdir -p ${AIRFLOW_HOME}/logs && \
    mkdir -p ${AIRFLOW_HOME}/plugins && \
    chown -R 50000:50000 ${AIRFLOW_HOME} && \
    chmod -R 755 ${AIRFLOW_HOME}

# 安装 Airflow（含 PostgreSQL 驱动约束）
RUN pip install --no-cache-dir --retries 15 \
    -i "${PIP_INDEX_URL}" \
    "apache-airflow[postgres]==${AIRFLOW_VERSION}" \
    --constraint "${CONSTRAINT_URL}" \
    psycopg2-binary

# 复制 DAG 依赖清单并安装项目 Python 依赖
COPY requirements-airflow.txt /tmp/requirements-airflow.txt
RUN pip install --no-cache-dir --retries 15 \
    -i "${PIP_TASK_DEPS_INDEX_URL}" \
    -r /tmp/requirements-airflow.txt

# 复制入口脚本并赋予执行权限
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 切换到 airflow 用户并设置工作目录
USER airflow
WORKDIR ${AIRFLOW_HOME}

# Web UI 端口
EXPOSE 8080

CMD ["/entrypoint.sh"]
