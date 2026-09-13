"""统一的大模型客户端，支持 Ollama 与 OpenAI 兼容接口。"""

import json
import logging
from typing import Any, Dict, List, Optional, Type

import httpx
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from src.config import Settings
from src.exceptions import OllamaConnectionError, OllamaException, OllamaTimeoutError
from src.services.ollama.prompts import RAGPromptBuilder, ResponseParser

logger = logging.getLogger(__name__)


class _OpenAICompatibleChatModel:
    """供 LangGraph 节点使用的轻量异步 ChatModel 适配器。"""

    def __init__(
        self,
        client: "OllamaClient",
        model: str,
        temperature: float,
        output_schema: Optional[Type[BaseModel]] = None,
    ):
        self.client = client
        self.model = model
        self.temperature = temperature
        self.output_schema = output_schema

    def with_structured_output(self, schema: Type[BaseModel]):
        return _OpenAICompatibleChatModel(self.client, self.model, self.temperature, schema)

    @staticmethod
    def _prompt_text(prompt: Any) -> str:
        if isinstance(prompt, str):
            return prompt
        if hasattr(prompt, "to_string"):
            return prompt.to_string()
        if isinstance(prompt, list):
            return "\n".join(str(getattr(item, "content", item)) for item in prompt)
        return str(prompt)

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end >= start:
            text = text[start : end + 1]
        return json.loads(text)

    async def ainvoke(self, prompt: Any, **_: Any):
        prompt_text = self._prompt_text(prompt)
        if self.output_schema is not None:
            schema = json.dumps(self.output_schema.model_json_schema(), ensure_ascii=False)
            prompt_text = (
                f"{prompt_text}\n\n"
                "请只返回一个合法 JSON 对象，不要使用 Markdown 代码块。"
                f"JSON 必须符合以下 schema：{schema}"
            )

        result = await self.client.generate(
            model=self.model,
            prompt=prompt_text,
            temperature=self.temperature,
        )
        content = (result or {}).get("response", "")
        if self.output_schema is not None:
            return self.output_schema.model_validate(self._parse_json(content))
        return AIMessage(content=content)


class OllamaClient:
    """保留原类名以兼容现有依赖注入，同时按配置选择 LLM 提供方。"""

    _OLLAMA_DEFAULTS = {
        "llama3.2:3b",
        "llama3.2:1b",
        "deepseek-r1",
        "deepseek-r1:7b",
        "qwen2.5:7b",
    }

    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = settings.llm_provider
        self.timeout = httpx.Timeout(float(settings.ollama_timeout))
        self.prompt_builder = RAGPromptBuilder()
        self.response_parser = ResponseParser()

        if self.provider == "openai":
            self.base_url = settings.openai_base_url.rstrip("/")
            self.api_key = settings.openai_api_key.get_secret_value()
            self.default_model = settings.openai_model
            self.fallback_model = settings.openai_model_fallback
            if not self.api_key:
                raise OllamaException("OPENAI_API_KEY 未配置")
        else:
            self.base_url = settings.ollama_host.rstrip("/")
            self.api_key = ""
            self.default_model = settings.ollama_model
            self.fallback_model = None

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.provider == "openai":
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _resolve_model(self, requested: Optional[str]) -> str:
        if not requested:
            return self.default_model
        if self.provider == "openai" and requested in self._OLLAMA_DEFAULTS:
            return self.default_model
        return requested

    def _candidate_models(self, requested: Optional[str]) -> List[str]:
        primary = self._resolve_model(requested)
        candidates = [primary]
        if self.provider == "openai" and self.fallback_model and self.fallback_model != primary:
            candidates.append(self.fallback_model)
        return candidates

    def get_langchain_model(self, model: str, temperature: float = 0.0):
        if self.provider == "openai":
            return _OpenAICompatibleChatModel(self, self._resolve_model(model), temperature)

        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, temperature=temperature, base_url=self.base_url)

    async def health_check(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.provider == "openai":
                    response = await client.get(f"{self.base_url}/models", headers=self._headers())
                    if response.status_code == 200:
                        return {
                            "status": "healthy",
                            "message": f"在线大模型服务运行正常（{self.default_model}）",
                        }
                    raise OllamaException(f"在线大模型服务返回状态码 {response.status_code}")

                response = await client.get(f"{self.base_url}/api/version")
                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "message": "Ollama 服务运行正常",
                        "version": response.json().get("version", "unknown"),
                    }
                raise OllamaException(f"Ollama 返回状态码 {response.status_code}")
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(f"无法连接到大模型服务: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(f"大模型服务请求超时: {exc}") from exc
        except OllamaException:
            raise
        except Exception as exc:
            raise OllamaException(f"大模型健康检查失败: {exc}") from exc

    async def list_models(self) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.provider == "openai":
                    response = await client.get(f"{self.base_url}/models", headers=self._headers())
                    response.raise_for_status()
                    return response.json().get("data", [])

                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                return response.json().get("models", [])
        except Exception as exc:
            raise OllamaException(f"获取模型列表出错: {exc}") from exc

    @staticmethod
    def _openai_usage(result: Dict[str, Any]) -> Dict[str, Any]:
        usage = result.get("usage") or {}
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }

    async def _generate_openai(self, model: str, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        for key in ("temperature", "top_p", "max_tokens", "seed", "stop"):
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs[key]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            if response.status_code != 200:
                raise OllamaException(f"模型 {model} 请求失败 ({response.status_code}): {response.text[:500]}")
            result = response.json()
            choices = result.get("choices") or []
            if not choices:
                raise OllamaException(f"模型 {model} 未返回 choices")
            content = choices[0].get("message", {}).get("content") or ""
            return {
                "response": content,
                "done": True,
                "model": result.get("model", model),
                "usage_metadata": self._openai_usage(result),
            }

    async def generate(self, model: str, prompt: str, stream: bool = False, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if self.provider == "openai":
            last_error: Optional[Exception] = None
            for candidate in self._candidate_models(model):
                try:
                    logger.info("调用在线大模型: model=%s, stream=%s", candidate, stream)
                    return await self._generate_openai(candidate, prompt, **kwargs)
                except Exception as exc:
                    last_error = exc
                    logger.warning("模型 %s 调用失败，尝试下一候选模型: %s", candidate, exc)
            raise OllamaException(f"所有在线模型均调用失败: {last_error}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                data = {"model": model, "prompt": prompt, "stream": stream, **kwargs}
                response = await client.post(f"{self.base_url}/api/generate", json=data)
                if response.status_code != 200:
                    raise OllamaException(f"文本生成失败: {response.status_code}")
                result = response.json()
                usage_metadata: Dict[str, Any] = {}
                if "prompt_eval_count" in result:
                    usage_metadata["prompt_tokens"] = result.get("prompt_eval_count", 0)
                if "eval_count" in result:
                    usage_metadata["completion_tokens"] = result.get("eval_count", 0)
                if usage_metadata:
                    usage_metadata["total_tokens"] = usage_metadata.get("prompt_tokens", 0) + usage_metadata.get(
                        "completion_tokens", 0
                    )
                if "total_duration" in result:
                    usage_metadata["latency_ms"] = round(result["total_duration"] / 1_000_000, 2)
                result["usage_metadata"] = usage_metadata
                return result
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(f"无法连接到 Ollama 服务: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(f"Ollama 服务请求超时: {exc}") from exc
        except OllamaException:
            raise
        except Exception as exc:
            raise OllamaException(f"调用 Ollama 生成文本出错: {exc}") from exc

    async def generate_stream(self, model: str, prompt: str, **kwargs: Any):
        if self.provider != "openai":
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                data = {"model": model, "prompt": prompt, "stream": True, **kwargs}
                async with client.stream("POST", f"{self.base_url}/api/generate", json=data) as response:
                    if response.status_code != 200:
                        raise OllamaException(f"流式生成失败: {response.status_code}")
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                yield json.loads(line)
                            except json.JSONDecodeError:
                                logger.warning("解析流式片段失败")
            return

        last_error: Optional[Exception] = None
        for candidate in self._candidate_models(model):
            emitted = False
            payload: Dict[str, Any] = {
                "model": candidate,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            }
            for key in ("temperature", "top_p", "max_tokens", "seed", "stop"):
                if key in kwargs and kwargs[key] is not None:
                    payload[key] = kwargs[key]
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            body = (await response.aread()).decode(errors="replace")[:500]
                            raise OllamaException(f"模型 {candidate} 流式请求失败 ({response.status_code}): {body}")
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                yield {"done": True, "model": candidate}
                                return
                            chunk = json.loads(data)
                            choices = chunk.get("choices") or []
                            content = choices[0].get("delta", {}).get("content") if choices else None
                            if content:
                                emitted = True
                                yield {"response": content, "done": False, "model": candidate}
                yield {"done": True, "model": candidate}
                return
            except Exception as exc:
                last_error = exc
                if emitted:
                    raise OllamaException(f"流式响应中断: {exc}") from exc
                logger.warning("模型 %s 流式调用失败，尝试下一候选模型: %s", candidate, exc)
        raise OllamaException(f"所有在线模型流式调用均失败: {last_error}")

    async def generate_rag_answer(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: str = "",
        use_structured_output: bool = False,
        short_term_history: Optional[List[Dict[str, str]]] = None,
        long_term_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        try:
            if use_structured_output:
                prompt_data = self.prompt_builder.create_structured_prompt(
                    query,
                    chunks,
                    short_term_history,
                    long_term_history,
                )
                response = await self.generate(
                    model=model,
                    prompt=prompt_data["prompt"],
                    temperature=0.7,
                    top_p=0.9,
                )
            else:
                prompt = self.prompt_builder.create_rag_prompt(
                    query,
                    chunks,
                    short_term_history,
                    long_term_history,
                )
                response = await self.generate(model=model, prompt=prompt, temperature=0.7, top_p=0.9)

            if not response or "response" not in response:
                raise OllamaException("大模型未返回有效结果")
            answer_text = response["response"]
            if use_structured_output:
                return self.response_parser.parse_structured_response(answer_text)

            sources = []
            seen_urls = set()
            for chunk in chunks:
                arxiv_id = chunk.get("arxiv_id")
                if arxiv_id:
                    clean_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
                    pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"
                    if pdf_url not in seen_urls:
                        sources.append(pdf_url)
                        seen_urls.add(pdf_url)
            citations = list({chunk.get("arxiv_id") for chunk in chunks if chunk.get("arxiv_id")})
            return {"answer": answer_text, "sources": sources, "confidence": "medium", "citations": citations[:5]}
        except Exception as exc:
            logger.error("生成 RAG 回答出错: %s", exc)
            raise OllamaException(f"生成 RAG 回答失败: {exc}") from exc

    async def generate_rag_answer_stream(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: str = "",
        short_term_history: Optional[List[Dict[str, str]]] = None,
        long_term_history: Optional[List[Dict[str, str]]] = None,
    ):
        prompt = self.prompt_builder.create_rag_prompt(
            query,
            chunks,
            short_term_history,
            long_term_history,
        )
        try:
            async for chunk in self.generate_stream(model=model, prompt=prompt, temperature=0.7, top_p=0.9):
                yield chunk
        except Exception as exc:
            logger.error("流式生成 RAG 回答出错: %s", exc)
            raise OllamaException(f"流式生成 RAG 回答失败: {exc}") from exc

    async def generate_memory_answer(
        self,
        query: str,
        model: str = "",
        short_term_history: Optional[List[Dict[str, str]]] = None,
        long_term_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        prompt = self.prompt_builder.create_memory_prompt(query, short_term_history, long_term_history)
        response = await self.generate(model=model, prompt=prompt, temperature=0.3, top_p=0.8)
        if not response or "response" not in response:
            raise OllamaException("大模型未返回有效的记忆回答")
        return str(response["response"])
