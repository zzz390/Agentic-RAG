# 注释策略：代码注释与 docstring 以中文为主，便于阅读维护
import os
from pathlib import Path
from typing import Annotated, List, Literal, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).parent.parent
#设置当前文件路径的前两级目录为根目录
ENV_FILE_PATH = PROJECT_ROOT / ".env"
#然后在根目录下取.env


class BaseConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        #接受的是一个列表，后面的会覆盖前面的，也就是说要是有后面那个就用后面那个
        env_file_encoding="utf-8-sig",
        #Windows 记事本、VS Code 保存文件时，经常自动给文件开头加一个看不见的符号 \ufeff，叫 BOM 头
        #直接UTF-8会把前面这个符号当成乱码，但是加一个sig会自动忽略这个BOM头
        extra="ignore",
        #在.env里面写了多余的、配置类里没定义的变量直接忽略，不报错
        frozen=True,
        #把配置变成只读模式，不会被修改
        env_nested_delimiter="__",
        #允许用双下划线表示嵌套配置
        case_sensitive=False,
        #环境变量名不区分大小写
    )
#这是一个通用配置加载模板，在项目所有配置场景里发挥作用

class ArxivSettings(BaseConfigSettings):
    #继承上面那个类BaseConfigSettings，但是下面又对arxiv进行特殊的配置
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="ARXIV__",
        #只读env里面以ARXIV__开头的环境变量
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    #核心API配置
    base_url: str = "https://export.arxiv.org/api/query"
    #接口入口，所有HTTP请求都往这个地址发
    pdf_cache_dir: str = "./data/arxiv_pdfs"
    #本地缓存目录，保存下载的PDF文件
    rate_limit_delay: float = 3.0
    #控制发送请求的间隔，不能狂发请求
    timeout_seconds: int = 30
    #请求超时时间，超过30秒没有响应就报错或者重试
    max_results: int = 15
    #最大单词查询返回结果数
    search_category: str = "cs.AI"
    #搜索的类别
    download_max_retries: int = 3
    download_retry_delay_base: float = 5.0
    max_concurrent_downloads: int = 5
    #异步下载的最大并发数
    max_concurrent_parsing: int = 1
    #解析PDF的最大并发数

    namespaces: dict = {
        "atom": "http://www.w3.org/2005/Atom",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    '''
    arxiv api返回的是XML格式：
    <atom:entry>
        <atom:title>论文标题</atom:title>
        <arxiv:doi>10.1234/xxx</arxiv:doi>
    </atom:entry>
    这里面的atom：  arxiv：  opensearch： 其实都是对应的一个网址
    比如说atom:真正名字是http://www.w3.org/2005/Atom，
    python看不懂，所以建一个namespaces字典，做一个缩写-网址的映射表
    '''


    @field_validator("pdf_cache_dir")
    #Field Validator会先调用下面那个validate_cache_dir类函数
    @classmethod
    #Pydantic对字段验证器的强制要求，把validate_cache_dir变成类方法
    def validate_cache_dir(cls, v: str) -> str:
    #定义了一个函数，接收1.配置类本身，2.v
        os.makedirs(v, exist_ok=True)
        #检查文件路径是否存在，不存在的话就创建
        return v
#总结一下，这个类函数会统一管理arxiv相关的参数，让程序启动时自动加载配置、创建目录、解析XML

class PDFParserSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="PDF_PARSER__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    max_pages: int = 30             #页数
    max_file_size_mb: int = 20      #文件大小不超过20MB
    do_ocr: bool = False            #光写字符识别，开启的话就能解析扫描件、图片版PDF
    do_table_structure: bool = True
    #是否解析PDF里的表格结构，开启的话能吧表格转换为数据化结构如字典、列表


class ChunkingSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="CHUNKING__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    chunk_size: int = 600
    overlap_size: int = 100
    min_chunk_size: int = 100
    section_based: bool = True
    #是否按章节或者段落边界分块，关闭就会按固定字符数强行分块


class OpenSearchSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="OPENSEARCH__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    host: str = "http://localhost:9200"
    #OpenSearch 服务的连接地址，默认是本地开发的地址localhost，也可以覆盖为线上地址
    #host和RUL的区别，就像是小区地址和具体门牌号的区别，host只定位服务器，URL是完整的请求地址
    index_name: str = "arxiv-papers"
    #主索引的名字，用来存储论文的元数据（标题、作者、摘要等）
    chunk_index_suffix: str = "chunks"
    #分块文本索引的后缀，和上面的主索引构成名字arxiv-papers-chunks
    max_text_size: int = 1000000

    vector_dimension: int = 512  # BAAI/bge-small-zh-v1.5
    vector_space_type: str = "cosinesimil"  #用余弦相似度检索

    rrf_pipeline_name: str = "hybrid-rrf-pipeline"
    #混合检索的 RRF（Reciprocal Rank Fusion）管道名称
    hybrid_search_size_multiplier: int = 2
    #结果的倍数，粗召回先召回两倍的量


class LangfuseSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        # Langfuse 官方环境变量使用单下划线，例如
        # LANGFUSE_PUBLIC_KEY、LANGFUSE_SECRET_KEY 和 LANGFUSE_HOST。
        env_prefix="LANGFUSE_",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    public_key: str = ""
    secret_key: str = ""
    host: str = "http://localhost:3000"
    #如果是自己部署，就用这个地址，如果用官方的就得换成官网提供的地址
    enabled: bool = True
    #是否开启监控，开启的话LLM调用、向量检索、分块操作都会被记录
    flush_at: int = 15  #达到多少条的时候就上传
    flush_interval: float = 1.0  #等待间隔
    max_retries: int = 3
    timeout: int = 30
    debug: bool = False  #不用很详细打印日志，只在必要的时候打印


class RedisSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="REDIS__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    decode_responses: bool = True
    socket_timeout: int = 30
    socket_connect_timeout: int = 30

    ttl_hours: int = 6  #6小时自动删除


class UploadSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="UPLOAD__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    upload_dir: str = "./data/uploads"
    max_file_size_mb: int = 50
    allowed_extensions: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: [".pdf", ".txt", ".md", ".docx", ".xlsx", ".xls"]
    )
    excel_max_rows: int = 500
    min_extracted_text_chars: int = 50

    @field_validator("upload_dir")
    @classmethod
    def validate_upload_dir(cls, v: str) -> str:
        os.makedirs(v, exist_ok=True)
        return v

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def parse_allowed_extensions(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("allowed_extensions")
    @classmethod
    def normalize_extensions(cls, extensions: List[str]) -> List[str]:
        normalized = []
        for ext in extensions:
            value = ext.strip().lower()
            if not value:
                continue
            if not value.startswith("."):
                value = f".{value}"
            normalized.append(value)
        if not normalized:
            raise ValueError("allowed_extensions must contain at least one extension")
        return normalized

    def resolved_upload_dir(self) -> Path:
        path = Path(self.upload_dir)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    def allowed_extension_set(self) -> set[str]:
        return set(self.allowed_extensions)


class EmbeddingsSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="EMBEDDINGS__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    model_name: str = "BAAI/bge-small-zh-v1.5"
    model_path: str = "./models/bge-small-zh-v1.5"
    device: Literal["cpu", "cuda", "mps"] = "cpu"
    batch_size: int = 32
    query_instruction: str = "为这个句子生成表示以用于检索相关文章："

    def resolved_model_path(self) -> str:
        path = Path(self.model_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path)


class Settings(BaseConfigSettings):
    app_version: str = "0.1.0"
    debug: bool = True
    environment: Literal["development", "staging", "production"] = "development"
    #开发、测试、生产不同的阶段
    service_name: str = "rag-api"

    postgres_database_url: str = "postgresql://rag_user:rag_password@localhost:5432/rag_db"
    postgres_echo_sql: bool = False
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 0

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout: int = 300

    # 大模型提供方。openai 模式兼容实现了 OpenAI Chat Completions 的服务。
    llm_provider: Literal["ollama", "openai"] = "ollama"
    openai_api_key: SecretStr = SecretStr("")
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_model_fallback: Optional[str] = None

    use_hybrid_search: bool = True

    embeddings: EmbeddingsSettings = Field(default_factory=EmbeddingsSettings)
    upload: UploadSettings = Field(default_factory=UploadSettings)
    arxiv: ArxivSettings = Field(default_factory=ArxivSettings)
    pdf_parser: PDFParserSettings = Field(default_factory=PDFParserSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)

    @field_validator("postgres_database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not (v.startswith("postgresql://") or v.startswith("postgresql+psycopg2://")):
            raise ValueError("Database URL must start with 'postgresql://' or 'postgresql+psycopg2://'")
        return v
#把所有子配置整合在一起，代码里只需要导入Settings一个入口，定义版本、环境、调用模式

def get_settings() -> Settings:
    return Settings()
#每一次调用settings都会读取env，加载很多配置创建很多子配置实例。
#用get_settings来获取settings，创建单例，程序只创建一次，之后都用同一个对象
#避免创建多次setting
