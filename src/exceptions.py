'''
给项目定义专用报错信息
'''

class RepositoryException(Exception):
    """仓库相关操作的基础异常类"""


class PaperNotFound(RepositoryException):
    """未找到论文数据时抛出"""


class PaperNotSaved(RepositoryException):
    """论文数据保存失败时抛出"""


class ParsingException(Exception):
    """解析相关错误的基础异常类"""


class PDFParsingException(ParsingException):
    """PDF 解析相关错误的基础异常类"""


class PDFValidationError(PDFParsingException):
    """PDF 文件校验失败时抛出"""


class PDFDownloadException(Exception):
    """PDF 下载相关错误的基础异常类"""


class PDFDownloadTimeoutError(PDFDownloadException):
    """PDF 下载超时抛出"""


class PDFCacheException(Exception):
    """PDF 缓存相关错误抛出"""


class OpenSearchException(Exception):
    """OpenSearch 相关错误的基础异常类"""


class ArxivAPIException(Exception):
    """arXiv API 相关错误的基础异常类"""


class ArxivAPITimeoutError(ArxivAPIException):
    """arXiv API 请求超时抛出"""


class ArxivAPIRateLimitError(ArxivAPIException):
    """超出 arXiv API 请求频率限制时抛出"""


class ArxivParseError(ArxivAPIException):
    """arXiv API 响应解析失败时抛出"""


class MetadataFetchingException(Exception):
    """元数据获取流程错误的基础异常类"""


class PipelineException(MetadataFetchingException):
    """数据管道执行过程中出错抛出"""


class LLMException(Exception):
    """LLM 相关错误的基础异常类"""


class OllamaException(LLMException):
    """Ollama 服务相关错误抛出"""


class OllamaConnectionError(OllamaException):
    """无法连接 Ollama 服务时抛出"""


class OllamaTimeoutError(OllamaException):
    """Ollama 服务请求超时抛出"""


class ConfigurationError(Exception):
    """配置无效或错误时抛出"""


class UploadException(Exception):
    """用户上传文档相关错误的基础异常类"""


class UploadValidationError(UploadException):
    """上传文件校验失败时抛出（格式、大小等）"""


class UnsupportedUploadFormatError(UploadValidationError):
    """不支持的文件扩展名时抛出"""


class UploadFileTooLargeError(UploadValidationError):
    """上传文件超过大小限制时抛出"""


class UploadParsingException(ParsingException):
    """上传文档解析失败或提取文本为空时抛出"""