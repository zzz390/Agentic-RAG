import os

import pytest
from src.config import Settings


def test_settings_initialization():
    """Settings 应能正常初始化。"""
    settings = Settings()

    assert settings.app_version == "0.1.0"
    assert settings.debug is True
    assert settings.environment == "development"
    assert settings.service_name == "rag-api"


def test_settings_postgres_defaults():
    """PostgreSQL 默认配置应符合预期。"""
    settings = Settings()

    assert "postgresql://" in settings.postgres_database_url
    assert settings.postgres_echo_sql is False
    assert settings.postgres_pool_size == 20
    assert settings.postgres_max_overflow == 0


def test_settings_opensearch_defaults():
    """OpenSearch 默认配置应符合预期。"""
    settings = Settings()

    assert settings.opensearch.host == "http://localhost:9200"
    assert settings.opensearch.index_name == "arxiv-papers"


def test_settings_ollama_defaults():
    """Ollama 默认配置应符合预期。"""
    settings = Settings()

    # Docker 环境下默认主机为 ollama 服务
    expected_host = "http://ollama:11434" if "OLLAMA_HOST" not in os.environ else settings.ollama_host
    assert settings.ollama_host in ["http://localhost:11434", "http://ollama:11434"]


def test_settings_upload_defaults():
    """上传模块默认配置应符合预期。"""
    settings = Settings()

    assert settings.upload.max_file_size_mb == 50
    assert ".pdf" in settings.upload.allowed_extension_set()
    assert ".docx" in settings.upload.allowed_extension_set()
    assert settings.upload.excel_max_rows == 500
    assert settings.upload.min_extracted_text_chars == 50
    assert settings.upload.resolved_upload_dir().exists()
