FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS base

WORKDIR /app

# 复制依赖声明文件
COPY pyproject.toml uv.lock ./

# UV_COMPILE_BYTECODE：生成 .pyc，加快应用启动。
# UV_LINK_MODE=copy：缓存与安装目录不在同一文件系统时避免硬链接相关告警。
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_HTTP_TIMEOUT=300 UV_HTTP_RETRIES=5

# 国内构建默认清华 PyPI；海外可 --build-arg UV_INDEX_URL=https://pypi.org/simple
ARG UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_INDEX_URL=${UV_INDEX_URL}

# uv.lock 已将 torch/torchvision 固定为 CPU 索引（download.pytorch.org/whl/cpu）
ARG UV_REWRITE_HOSTED_PACKAGES=true
RUN if [ "$UV_REWRITE_HOSTED_PACKAGES" = "true" ]; then \
      sed -i 's|https://files.pythonhosted.org/packages|https://pypi.tuna.tsinghua.edu.cn/packages|g' uv.lock; \
    fi

# PyTorch CPU 轮子仍走官方索引（~200MB，无 nvidia-*）；清华 pytorch 镜像常缺 +cpu 包

# Debian apt 源（bookworm）改用清华，加速基础系统包
RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g; s|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g; s|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list 2>/dev/null || true

# 安装依赖（不使用仅 BuildKit 支持的 mount 参数）
RUN uv sync --frozen --no-dev

# 复制业务源码
COPY src /app/src

FROM python:3.12.8-slim AS final

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ARG VERSION=0.1.0
ENV APP_VERSION=$VERSION

WORKDIR /app

COPY --from=base /app /app

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
