import json
import logging
import os
import uuid
from pathlib import Path
from typing import AsyncIterator, Iterator

import gradio as gr
import httpx

logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000/api/v1"
DEFAULT_MODEL = "qwen3.8-flash"
# Agentic 多轮 LLM（护栏/改写/打分/生成），常超过 5 分钟
AGENTIC_HTTP_TIMEOUT = 900.0
UPLOAD_FILE_TYPES = [".pdf", ".txt", ".md", ".docx", ".xlsx", ".xls"]
MODEL_CHOICES = ["qwen3.8-flash", "qwen3.7-flash"]

CUSTOM_CSS = """
:root {
    --ink: #17233b;
    --muted: #65738b;
    --line: rgba(38, 58, 92, 0.12);
    --panel: rgba(255, 255, 255, 0.88);
    --violet: #6d5dfc;
    --blue: #3388ff;
    --mint: #37c9a5;
}

body, .gradio-container {
    background:
        radial-gradient(circle at 8% 0%, rgba(109, 93, 252, 0.13), transparent 28rem),
        radial-gradient(circle at 92% 8%, rgba(51, 136, 255, 0.12), transparent 30rem),
        #f6f8fc !important;
    color: var(--ink);
}

.gradio-container {
    max-width: 1380px !important;
    margin: 0 auto !important;
    padding: 28px 26px 42px !important;
}

.app-shell { gap: 18px !important; }

.hero {
    position: relative;
    overflow: hidden;
    padding: 32px 36px !important;
    border: 0 !important;
    border-radius: 24px !important;
    background: linear-gradient(125deg, #182643 0%, #293e70 54%, #5a50d8 100%) !important;
    box-shadow: 0 22px 55px rgba(37, 48, 91, 0.2);
}

.hero::after {
    content: "";
    position: absolute;
    width: 340px;
    height: 340px;
    right: -95px;
    top: -170px;
    border-radius: 50%;
    border: 54px solid rgba(255, 255, 255, 0.08);
}

.hero h1 {
    margin: 8px 0 10px !important;
    color: #fff !important;
    font-size: clamp(2rem, 4vw, 3.35rem) !important;
    line-height: 1.05 !important;
    letter-spacing: -0.045em;
}

.hero p {
    max-width: 780px;
    margin: 0 !important;
    color: rgba(255,255,255,.75) !important;
    font-size: 1.02rem !important;
    line-height: 1.7 !important;
}

.eyebrow {
    display: inline-flex;
    align-items: center;
    padding: 6px 11px;
    border: 1px solid rgba(255,255,255,.18);
    border-radius: 999px;
    background: rgba(255,255,255,.1);
    color: #dce4ff;
    font-size: .72rem;
    font-weight: 700;
    letter-spacing: .14em;
    text-transform: uppercase;
}

.hero-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 9px;
    margin-top: 22px;
}

.hero-chip {
    padding: 7px 11px;
    border-radius: 999px;
    background: rgba(255,255,255,.1);
    color: rgba(255,255,255,.9);
    font-size: .78rem;
}

.status-bar, .settings-panel, .workspace-tabs, .upload-card {
    border: 1px solid var(--line) !important;
    border-radius: 18px !important;
    background: var(--panel) !important;
    box-shadow: 0 10px 30px rgba(37, 54, 88, 0.07);
    backdrop-filter: blur(12px);
}

.status-bar { padding: 10px 12px !important; align-items: center !important; }
.status-copy { padding: 2px 8px !important; }
.status-copy p { margin: 0 !important; color: var(--muted) !important; }

.settings-panel { padding: 4px 12px !important; }
.settings-panel > .label-wrap { font-weight: 700 !important; color: var(--ink) !important; }

.workspace-tabs { padding: 10px !important; }
.workspace-tabs .tab-nav { gap: 6px; border-bottom: 0 !important; padding: 2px 4px 12px; }
.workspace-tabs .tab-nav button {
    border: 0 !important;
    border-radius: 12px !important;
    color: var(--muted) !important;
    font-weight: 650 !important;
    padding: 10px 16px !important;
}
.workspace-tabs .tab-nav button.selected {
    background: #eef0ff !important;
    color: #5144dc !important;
}

.mode-intro { padding: 8px 4px 2px !important; }
.mode-intro h3 { margin: 0 0 5px !important; color: var(--ink) !important; }
.mode-intro p { margin: 0 !important; color: var(--muted) !important; }

.chat-window {
    border: 1px solid var(--line) !important;
    border-radius: 18px !important;
    background: linear-gradient(180deg, #fbfcff 0%, #f7f9fd 100%) !important;
    overflow: hidden;
}
.chat-window .message {
    border-radius: 16px !important;
    box-shadow: none !important;
}
.chat-window .message.user {
    background: linear-gradient(135deg, #6254eb, #427de8) !important;
    color: white !important;
}
.chat-window .message.bot {
    border: 1px solid var(--line) !important;
    background: white !important;
}

.composer textarea { font-size: 1rem !important; line-height: 1.6 !important; }
.composer, .upload-card { border-radius: 16px !important; }

.primary-action {
    border: 0 !important;
    border-radius: 12px !important;
    background: linear-gradient(135deg, var(--violet), var(--blue)) !important;
    color: #fff !important;
    font-weight: 700 !important;
    box-shadow: 0 9px 20px rgba(82, 78, 221, .24) !important;
}
.secondary-action { border-radius: 12px !important; font-weight: 650 !important; }

.memory-note {
    padding: 9px 12px !important;
    border-left: 3px solid var(--mint) !important;
    border-radius: 0 10px 10px 0 !important;
    background: #f0fbf8 !important;
}
.memory-note p { margin: 0 !important; color: #397665 !important; font-size: .84rem !important; }

.upload-card { padding: 20px !important; }
.footer-note { padding: 12px 6px 0 !important; text-align: center; }
.footer-note p { color: var(--muted) !important; font-size: .82rem !important; }
.footer-note a { color: #5d55dd !important; text-decoration: none !important; }

@media (max-width: 720px) {
    .gradio-container { padding: 14px 12px 28px !important; }
    .hero { padding: 24px 22px !important; border-radius: 19px !important; }
    .hero h1 { font-size: 2.2rem !important; }
    .workspace-tabs { padding: 6px !important; }
}
"""


async def check_api_health() -> str:
    """检查 FastAPI 是否可用。"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{API_BASE_URL}/health")
        if response.status_code == 200:
            return f"✅ API 正常（{API_BASE_URL}）"
        return f"⚠️ API 返回 HTTP {response.status_code}"
    except httpx.RequestError as exc:
        return f"❌ 无法连接 API: {exc}\n请先启动后端（docker compose up 或 uvicorn）。"


def _format_sources(
    sources: list[str],
    chunks_used: int,
    search_mode: str,
    memory_used: bool = False,
    short_term_messages: int = 0,
    long_term_messages: int = 0,
) -> str:
    block = f"\n\n**检索信息**\n- 模式: {search_mode or '未知'}\n- 使用 chunk 数: {chunks_used}\n"
    if sources:
        block += f"- 来源数: {len(sources)}\n"
        for index, source in enumerate(sources[:3], 1):
            label = source.split("/")[-1] if "/" in source else source
            block += f"  {index}. [{label}]({source})\n"
        if len(sources) > 3:
            block += f"  … 另有 {len(sources) - 3} 条\n"
    block += (
        "\n**记忆状态**\n"
        f"- 本次使用历史: {'是' if memory_used else '否'}\n"
        f"- 短期消息: {short_term_messages} / 长期消息: {long_term_messages}\n"
    )
    return block


async def stream_standard_response(
    query: str,
    top_k: int,
    use_hybrid: bool,
    model: str,
    categories: str,
    session_id: str = "",
    user_id: str = "local_user",
    enable_memory: bool = True,
) -> Iterator[str]:
    """流式标准 RAG（/stream）。"""
    if not query.strip():
        yield "请输入问题。"
        return

    category_list = [cat.strip() for cat in categories.split(",") if cat.strip()] if categories else None
    payload = {
        "query": query,
        "top_k": top_k,
        "use_hybrid": use_hybrid,
        "model": model,
        "categories": category_list,
        "session_id": session_id or None,
        "user_id": user_id.strip() or "local_user",
        "enable_memory": enable_memory,
    }

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", f"{API_BASE_URL}/stream", json=payload) as response:
                if response.status_code != 200:
                    yield f"请求失败: HTTP {response.status_code}"
                    return

                current_answer = ""
                sources: list[str] = []
                chunks_used = 0
                search_mode = ""
                memory_used = False
                short_term_messages = 0
                long_term_messages = 0

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

                    if "error" in data:
                        yield f"错误: {data['error']}"
                        return

                    if "sources" in data:
                        sources = data.get("sources", [])
                        chunks_used = data.get("chunks_used", 0)
                        search_mode = data.get("search_mode", "")
                        memory_used = data.get("memory_used", memory_used)
                        short_term_messages = data.get("short_term_messages", short_term_messages)
                        long_term_messages = data.get("long_term_messages", long_term_messages)

                    if "chunk" in data:
                        current_answer += data["chunk"]
                        yield current_answer + _format_sources(
                            sources,
                            chunks_used,
                            search_mode,
                            memory_used,
                            short_term_messages,
                            long_term_messages,
                        )

                    if data.get("done"):
                        final = data.get("answer", current_answer)
                        yield final + _format_sources(
                            sources,
                            chunks_used,
                            search_mode,
                            memory_used,
                            short_term_messages,
                            long_term_messages,
                        )
                        break
    except httpx.RequestError as exc:
        yield f"连接失败: {exc}"


async def ask_agentic_response(
    query: str,
    top_k: int,
    use_hybrid: bool,
    model: str,
    categories: str,
    session_id: str = "",
    user_id: str = "local_user",
    enable_memory: bool = True,
) -> str:
    """Agentic RAG（/ask-agentic）。"""
    if not query.strip():
        return "请输入问题。"

    category_list = [cat.strip() for cat in categories.split(",") if cat.strip()] if categories else None
    payload = {
        "query": query,
        "top_k": top_k,
        "use_hybrid": use_hybrid,
        "model": model,
        "categories": category_list,
        "session_id": session_id or None,
        "user_id": user_id.strip() or "local_user",
        "enable_memory": enable_memory,
    }

    try:
        async with httpx.AsyncClient(timeout=AGENTIC_HTTP_TIMEOUT) as client:
            response = await client.post(f"{API_BASE_URL}/ask-agentic", json=payload)
        if response.status_code != 200:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            return f"Agentic 请求失败（HTTP {response.status_code}）: {detail}"

        data = response.json()
        answer = data.get("answer", "")
        reasoning = data.get("reasoning_steps", [])
        attempts = data.get("retrieval_attempts", 0)
        sources = data.get("sources", [])
        search_mode = data.get("search_mode", "")

        text = answer + _format_sources(
            sources,
            data.get("chunks_used", top_k),
            search_mode,
            data.get("memory_used", False),
            data.get("short_term_messages", 0),
            data.get("long_term_messages", 0),
        )
        text += f"\n\n**Agentic 信息**\n- 检索轮次: {attempts}\n- 检索模式: {search_mode}\n"
        if reasoning:
            text += "- 推理步骤:\n"
            for step in reasoning:
                text += f"  - {step}\n"
        return text
    except httpx.ReadTimeout:
        return (
            "请求超时：Agentic 流程较慢（护栏→检索→打分→生成），通常需 5～10 分钟。\n"
            "请确认后端仍在运行（docker logs rag-api --tail 20），然后重试或稍后再看 API 日志是否已完成。"
        )
    except httpx.RequestError as exc:
        detail = str(exc).strip() or repr(exc)
        return f"连接失败: {detail}"


def _copy_history(history: list[dict] | None) -> list[dict]:
    return [dict(message) for message in (history or [])]


async def stream_standard_chat(
    query: str,
    history: list[dict] | None,
    session_id: str,
    user_id: str,
    enable_memory: bool,
    top_k: int,
    use_hybrid: bool,
    model: str,
    categories: str,
) -> AsyncIterator[tuple[str, list[dict], str]]:
    history = _copy_history(history)
    if not query.strip():
        yield "", history, session_id
        return

    session_id = session_id or uuid.uuid4().hex
    history.extend(
        [
            {"role": "user", "content": query},
            {"role": "assistant", "content": "正在检索并结合会话记忆…"},
        ]
    )
    yield "", _copy_history(history), session_id

    async for answer in stream_standard_response(
        query,
        top_k,
        use_hybrid,
        model,
        categories,
        session_id,
        user_id,
        enable_memory,
    ):
        history[-1]["content"] = answer
        yield "", _copy_history(history), session_id


async def ask_agentic_chat(
    query: str,
    history: list[dict] | None,
    session_id: str,
    user_id: str,
    enable_memory: bool,
    top_k: int,
    use_hybrid: bool,
    model: str,
    categories: str,
) -> tuple[str, list[dict], str]:
    history = _copy_history(history)
    if not query.strip():
        return "", history, session_id

    session_id = session_id or uuid.uuid4().hex
    history.append({"role": "user", "content": query})
    answer = await ask_agentic_response(
        query,
        top_k,
        use_hybrid,
        model,
        categories,
        session_id,
        user_id,
        enable_memory,
    )
    history.append({"role": "assistant", "content": answer})
    return "", history, session_id


def new_conversation() -> tuple[list[dict], str, str]:
    session_id = uuid.uuid4().hex
    return [], session_id, f"✅ 已创建新会话 `{session_id[:8]}`；短期记忆已清空，长期记忆继续保留。"


async def upload_document(file_path: str | None, title: str = "") -> str:
    """上传文档到知识库。"""
    if not file_path:
        return "请先选择文件。"

    path = Path(file_path)
    if not path.exists():
        return f"文件不存在: {file_path}"

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            with path.open("rb") as handle:
                files = {"file": (path.name, handle, "application/octet-stream")}
                data = {"title": title.strip()} if title.strip() else {}
                response = await client.post(f"{API_BASE_URL}/documents/upload", files=files, data=data)

        if response.status_code != 200:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            return f"上传失败（HTTP {response.status_code}）: {detail}"

        payload = response.json()
        doc_id = payload.get("arxiv_id")
        return (
            f"**上传成功**\n\n"
            f"- 标题: {payload.get('title')}\n"
            f"- 文档 ID: `{doc_id}`\n"
            f"- 解析器: {payload.get('parser_used')}\n"
            f"- 分块: {payload.get('chunks_created')} / 已索引: {payload.get('chunks_indexed')}\n"
            f"- 状态: {payload.get('status')}\n\n"
            f"全文 API: `GET /api/v1/papers/{doc_id}`"
        )
    except httpx.RequestError as exc:
        return f"连接 API 失败: {exc}"


def _build_theme() -> gr.themes.Base:
    """返回与自定义 CSS 配套的浅色主题。"""
    return gr.themes.Soft(
        primary_hue="indigo",
        secondary_hue="blue",
        neutral_hue="slate",
        font=[gr.themes.GoogleFont("Inter"), "PingFang SC", "sans-serif"],
    ).set(
        button_large_radius="12px",
        input_radius="12px",
        block_radius="16px",
    )


def create_gradio_interface() -> gr.Blocks:
    """构建 Gradio 演示界面。"""

    with gr.Blocks(
        title="ScholarFlow · 智能论文研究台",
        fill_width=True,
    ) as interface:
        with gr.Column(elem_classes="app-shell"):
            gr.HTML(
                """
                <section class="hero">
                  <span class="eyebrow">Agentic knowledge workspace</span>
                  <h1>ScholarFlow</h1>
                  <p>面向论文与私有文档的智能研究台。融合混合检索、会话记忆与多步 Agent，
                  让每一次回答都更有依据、更贴近你的研究上下文。</p>
                  <div class="hero-chips">
                    <span class="hero-chip">✦ BM25 + BGE</span>
                    <span class="hero-chip">◈ 会话记忆</span>
                    <span class="hero-chip">⌁ 流式回答</span>
                    <span class="hero-chip">◎ 来源追溯</span>
                  </div>
                </section>
                """
            )

        with gr.Row(elem_classes="status-bar"):
            health_output = gr.Markdown(
                "**服务状态**　等待检测 · API `localhost:8000`",
                elem_classes="status-copy",
                scale=5,
            )
            health_btn = gr.Button("检测连接", size="sm", elem_classes="secondary-action", scale=1)
        health_btn.click(fn=check_api_health, outputs=health_output)

        with gr.Accordion("⚙️ 检索与记忆设置", open=False, elem_classes="settings-panel"):
            with gr.Row():
                top_k = gr.Slider(1, 10, value=3, step=1, label="检索片段数", scale=2)
                model_choice = gr.Dropdown(
                    choices=MODEL_CHOICES,
                    value=DEFAULT_MODEL,
                    label="生成模型",
                    scale=1,
                )
            with gr.Row():
                categories = gr.Textbox(
                    label="arXiv 分类过滤",
                    placeholder="例如 cs.AI, cs.LG（留空则不过滤）",
                    scale=2,
                )
                user_id = gr.Textbox(
                    value="local_user",
                    label="记忆空间",
                    placeholder="例如 researcher_01",
                    scale=1,
                )
            with gr.Row():
                use_hybrid = gr.Checkbox(value=True, label="启用混合检索 · BM25 + BGE")
                enable_memory = gr.Checkbox(value=True, label="启用短期与跨会话记忆")

        rag_params = [top_k, use_hybrid, model_choice, categories]

        with gr.Tabs(elem_classes="workspace-tabs"):
            with gr.Tab("快速问答"):
                # None ensures every browser session gets a fresh ID on its first message.
                std_session = gr.State(None)
                gr.Markdown(
                    "### 快速问答\n流式生成，适合日常论文检索与连续追问。",
                    elem_classes="mode-intro",
                )
                std_chat = gr.Chatbot(
                    label=None,
                    height=520,
                    placeholder="向你的知识库提问\n\n支持连续追问，也可以直接使用“它”“上一点”等指代。",
                    layout="bubble",
                    elem_classes="chat-window",
                )
                q_std = gr.Textbox(
                    label="你的问题",
                    placeholder="例如：用直观的方式解释 Transformer 的注意力机制…",
                    lines=2,
                    elem_classes="composer",
                )
                with gr.Row():
                    btn_std = gr.Button("发送问题  →", variant="primary", elem_classes="primary-action", scale=4)
                    new_std = gr.Button("新建会话", elem_classes="secondary-action", scale=1)
                std_memory_status = gr.Markdown(
                    "记忆已开启 · 保留最近 6 轮上下文，长期记忆按空间隔离。",
                    elem_classes="memory-note",
                )
                std_inputs = [
                    q_std,
                    std_chat,
                    std_session,
                    user_id,
                    enable_memory,
                    *rag_params,
                ]
                btn_std.click(
                    fn=stream_standard_chat,
                    inputs=std_inputs,
                    outputs=[q_std, std_chat, std_session],
                )
                q_std.submit(
                    fn=stream_standard_chat,
                    inputs=std_inputs,
                    outputs=[q_std, std_chat, std_session],
                )
                new_std.click(fn=new_conversation, outputs=[std_chat, std_session, std_memory_status])

            with gr.Tab("深度研究"):
                agent_session = gr.State(None)
                gr.Markdown(
                    "### 深度研究\n多步检索、相关性打分与问题改写，适合复杂问题。通常需要 5–10 分钟。",
                    elem_classes="mode-intro",
                )
                agent_chat = gr.Chatbot(
                    label=None,
                    height=520,
                    placeholder="提出一个需要多步检索与推理的研究问题。",
                    layout="bubble",
                    elem_classes="chat-window",
                )
                q_ag = gr.Textbox(
                    label="研究问题",
                    placeholder="例如：对比近三年 RAG 评估方法的演进与局限…",
                    lines=2,
                    elem_classes="composer",
                )
                with gr.Row():
                    btn_ag = gr.Button("开始深度研究  →", variant="primary", elem_classes="primary-action", scale=4)
                    new_ag = gr.Button("新建会话", elem_classes="secondary-action", scale=1)
                agent_memory_status = gr.Markdown(
                    "Agent 将自动执行护栏检查、检索、打分、必要时改写问题并再次检索。",
                    elem_classes="memory-note",
                )
                agent_inputs = [
                    q_ag,
                    agent_chat,
                    agent_session,
                    user_id,
                    enable_memory,
                    *rag_params,
                ]
                btn_ag.click(
                    fn=ask_agentic_chat,
                    inputs=agent_inputs,
                    outputs=[q_ag, agent_chat, agent_session],
                )
                q_ag.submit(
                    fn=ask_agentic_chat,
                    inputs=agent_inputs,
                    outputs=[q_ag, agent_chat, agent_session],
                )
                new_ag.click(fn=new_conversation, outputs=[agent_chat, agent_session, agent_memory_status])

            with gr.Tab("知识库"):
                gr.Markdown(
                    "### 扩充知识库\n上传本地资料，系统会自动解析、切分并建立混合检索索引。",
                    elem_classes="mode-intro",
                )
                with gr.Group(elem_classes="upload-card"):
                    up_file = gr.File(
                        label="拖放文档到这里",
                        file_types=UPLOAD_FILE_TYPES,
                        type="filepath",
                    )
                    up_title = gr.Textbox(label="自定义标题（可选）", placeholder="留空时使用文件名")
                    up_btn = gr.Button("解析并加入知识库  →", variant="primary", elem_classes="primary-action")
                    up_status = gr.Markdown("支持 PDF、Word、Markdown、文本和 Excel 文件。")
                    up_btn.click(fn=upload_document, inputs=[up_file, up_title], outputs=up_status)

        gr.Markdown(
            """
            ScholarFlow · 本地优先的智能研究工作台　·　
            [API 文档](http://localhost:8000/docs) ·
            [RAG 模式说明](docs/RAG-modes.md) ·
            [缓存策略](docs/cache.md) ·
            [BGE 嵌入](docs/embeddings.md)
            """,
            elem_classes="footer-note",
        )

    return interface


def main() -> None:
    # Gradio performs a localhost startup check; keep it off system HTTP proxies.
    for key in ("NO_PROXY", "no_proxy"):
        current = os.environ.get(key, "")
        hosts = [item.strip() for item in current.split(",") if item.strip()]
        for host in ("localhost", "127.0.0.1", "0.0.0.0"):
            if host not in hosts:
                hosts.append(host)
        os.environ[key] = ",".join(hosts)

    print("🚀 启动 Gradio 演示界面...")
    print(f"📡 后端 API: {API_BASE_URL}")
    interface = create_gradio_interface()
    interface.launch(
        server_name="0.0.0.0",
        server_port=7861,
        share=False,
        show_error=True,
        theme=_build_theme(),
        css=CUSTOM_CSS,
    )


if __name__ == "__main__":
    main()
