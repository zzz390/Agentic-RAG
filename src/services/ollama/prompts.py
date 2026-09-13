'''
RAGPromptBuilder：把系统提示、检索到的论文片段、用户问题拼成完整提示词
ResponseParser：把模型返回的 JSON / 半 JSON / 纯文本答案安全解析成标准格式，保证程序不崩溃
'''
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from src.schemas.ollama import RAGResponse

#RAG 提示词构建类，用于生成标准的 RAG 提示词
class RAGPromptBuilder:
    def __init__(self):
        """初始化提示词构建器"""
        # 获取当前文件所在目录下的 prompts 文件夹路径
        self.prompts_dir = Path(__file__).parent / "prompts"
        # 加载系统提示词
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        #从文本文件加载系统提示词
        prompt_file = self.prompts_dir / "rag_system.txt"
        if not prompt_file.exists():
            # 如果文件不存在，使用默认提示词
            return (
                "You are an AI assistant specialized in answering questions about "
                "academic papers from arXiv. Base your answer STRICTLY on the provided "
                "paper excerpts."
            )
        return prompt_file.read_text().strip()

    @staticmethod
    def _format_history(messages: Optional[List[Dict[str, str]]]) -> str:
        lines = []
        for message in messages or []:
            role = "用户" if message.get("role") == "user" else "助手"
            content = str(message.get("content", "")).strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def create_rag_prompt(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        short_term_history: Optional[List[Dict[str, str]]] = None,
        long_term_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """根据用户问题和检索到的文本块构建完整 RAG 提示词

        参数：
            query: 用户问题
            chunks: 从数据库检索到的文本块列表（含元数据）

        返回：
            格式化后的完整提示词
        """
        prompt = f"{self.system_prompt}\n\n"
        long_memory = self._format_history(long_term_history)
        short_memory = self._format_history(short_term_history)
        if long_memory:
            prompt += "### 跨会话长期记忆（可能不完整，仅用于保持对话连续性）:\n"
            prompt += f"{long_memory}\n\n"
        if short_memory:
            prompt += "### 当前会话最近对话:\n"
            prompt += f"{short_memory}\n\n"

        prompt += "### 论文上下文信息:\n\n"

        for i, chunk in enumerate(chunks, 1):
            # 获取文本块内容
            chunk_text = chunk.get("chunk_text", chunk.get("content", ""))
            arxiv_id = chunk.get("arxiv_id", "")

            # 加入最小元数据：仅论文编号用于引用
            prompt += f"[{i}. arXiv:{arxiv_id}]\n"
            prompt += f"{chunk_text}\n\n"

        prompt += f"### 用户问题:\n{query}\n\n"
        prompt += (
            "### 回答要求:\n请用自然、对话式的语言回答（不要返回JSON），并使用 [arXiv:id] 格式标注来源。\n\n"
        )

        return prompt

    def create_memory_prompt(
        self,
        query: str,
        short_term_history: Optional[List[Dict[str, str]]] = None,
        long_term_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Answer a follow-up that can be resolved from conversation memory alone."""
        return (
            "你是一个支持多轮对话的学术助手。请仅根据下面的会话记忆回答当前问题；"
            "如果记忆不足，请明确说明不知道，不要编造。\n\n"
            f"### 跨会话长期记忆:\n{self._format_history(long_term_history) or '无'}\n\n"
            f"### 当前会话最近对话:\n{self._format_history(short_term_history) or '无'}\n\n"
            f"### 当前问题:\n{query}\n"
        )

    def create_structured_prompt(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        short_term_history: Optional[List[Dict[str, str]]] = None,
        long_term_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """为模型构建带结构化输出格式的提示词

        参数：
            query: 用户问题
            chunks: 检索到的文本块

        返回：
            包含提示词和JSON格式约束的字典（供模型使用）
        """
        prompt_text = self.create_rag_prompt(query, chunks, short_term_history, long_term_history)

        # 返回提示词 + Pydantic 模型定义的JSON结构
        return {
            "prompt": prompt_text,
            "format": RAGResponse.model_json_schema(),
        }

#大模型返回结果解析器
class ResponseParser:
    @staticmethod
    def parse_structured_response(response: str) -> Dict[str, Any]:
        """解析模型返回的结构化结果

        参数：
            response: 模型原始返回字符串

        返回：
            解析后的字典格式数据
        """
        try:
            # 尝试直接解析JSON并通过Pydantic校验
            parsed_json = json.loads(response)
            validated_response = RAGResponse(**parsed_json)
            return validated_response.model_dump()
        except (json.JSONDecodeError, ValidationError):
            # 解析失败：使用备用方案从文本中提取JSON
            return ResponseParser._extract_json_fallback(response)

    @staticmethod
    def _extract_json_fallback(response: str) -> Dict[str, Any]:
        """备用方案：从返回文本中提取JSON内容

        参数：
            response: 模型原始返回内容

        返回：
            提取后的字典数据
        """
        # 正则查找 {...} 格式的JSON
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                # 使用Pydantic校验，缺失字段自动使用默认值
                validated = RAGResponse(**parsed)
                return validated.model_dump()
            except (json.JSONDecodeError, ValidationError):
                pass

        # 最终兜底：直接把返回内容当作文本答案
        return {
            "answer": response,
            "sources": [],
            "confidence": "low",
            "citations": [],
        }
