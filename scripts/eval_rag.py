#!/usr/bin/env python3
"""批量对比标准/Agentic RAG，并用 Ragas 评估忠实度与检索质量。"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_QUESTIONS = Path(__file__).parent / "eval_questions.jsonl"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "eval_results"
RAGAS_FIELDS = ("faithfulness", "context_precision", "factual_correctness", "context_recall")


def load_questions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Question file not found: {path}")

    questions: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_no} of {path}: {exc}") from exc
        if not isinstance(item.get("query"), str) or not item["query"].strip():
            raise ValueError(f"Missing or empty 'query' on line {line_no} of {path}")
        if "reference" in item and not isinstance(item["reference"], str):
            raise ValueError(f"'reference' must be a string on line {line_no} of {path}")
        questions.append(item)
    return questions


async def call_endpoint(
    client: httpx.AsyncClient,
    path: str,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any] | None, float, str | None]:
    started = time.perf_counter()
    try:
        response = await client.post(path, json=payload)
        latency_ms = (time.perf_counter() - started) * 1000
        if response.status_code == 200:
            return response.status_code, response.json(), latency_ms, None
        return response.status_code, None, latency_ms, response.text
    except httpx.HTTPError as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        return 0, None, latency_ms, str(exc)


def _serialize_sources(sources: Any) -> str:
    if not isinstance(sources, list):
        return str(sources or "")
    return " | ".join(
        item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, sort_keys=True)
        for item in sources
    )


def row_from_response(
    query: str,
    mode: str,
    status_code: int,
    latency_ms: float,
    data: dict[str, Any] | None,
    error: str | None,
    *,
    notes: str = "",
    reference: str = "",
) -> dict[str, Any]:
    data = data or {}
    contexts = data.get("retrieved_contexts", [])
    if not isinstance(contexts, list):
        contexts = []
    steps = data.get("reasoning_steps", [])

    return {
        "query": query,
        "reference": reference,
        "notes": notes,
        "mode": mode,
        "status_code": status_code,
        "latency_ms": round(latency_ms, 1),
        "answer": data.get("answer", ""),
        "sources": _serialize_sources(data.get("sources", [])),
        "retrieved_contexts": json.dumps(contexts, ensure_ascii=False),
        "chunks_used": data.get("chunks_used", ""),
        "search_mode": data.get("search_mode", ""),
        "retrieval_attempts": data.get("retrieval_attempts", ""),
        "reasoning_steps": " | ".join(str(step) for step in steps) if isinstance(steps, list) else str(steps),
        "faithfulness": "",
        "context_precision": "",
        "factual_correctness": "",
        "context_recall": "",
        "unsupported_response": "",
        "ragas_error": "",
        "error": error or "",
        "manual_score_1_to_5": "",
        "manual_comment": "",
    }


async def apply_ragas_scores(
    rows: list[dict[str, Any]],
    *,
    api_key: str,
    base_url: str,
    judge_model: str,
    threshold: float,
    timeout: float,
) -> None:
    try:
        from src.evaluation import RagasEvaluator
    except ImportError as exc:
        raise RuntimeError("Ragas 依赖未安装，请执行: pip install -e '.[eval]'") from exc

    evaluator = RagasEvaluator(
        api_key=api_key,
        base_url=base_url,
        model=judge_model,
        timeout=timeout,
    )
    try:
        for index, row in enumerate(rows, start=1):
            if row["status_code"] != 200:
                row["ragas_error"] = "endpoint request failed"
                continue
            contexts = json.loads(row["retrieved_contexts"])
            print(f"Ragas scoring {index}/{len(rows)}: {row['mode']} - {row['query'][:50]}")
            scores = await evaluator.evaluate(
                user_input=row["query"],
                response=row["answer"],
                retrieved_contexts=contexts,
                reference=row["reference"] or None,
            )
            row.update(scores.to_dict())
            if scores.faithfulness is not None:
                row["unsupported_response"] = scores.faithfulness < threshold
    finally:
        await evaluator.close()


def _metric_mean(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if isinstance(row.get(field), (int, float))]
    return round(statistics.fmean(values), 4) if values else None


def _summarize_rows(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    faithfulness_rows = [row for row in rows if isinstance(row.get("faithfulness"), (int, float))]
    unsupported = sum(float(row["faithfulness"]) < threshold for row in faithfulness_rows)
    return {
        "requests": len(rows),
        "successful_requests": sum(row.get("status_code") == 200 for row in rows),
        "faithfulness_scored": len(faithfulness_rows),
        "unsupported_responses": unsupported,
        "observed_unsupported_response_rate": (
            round(unsupported / len(faithfulness_rows), 4) if faithfulness_rows else None
        ),
        **{f"mean_{field}": _metric_mean(rows, field) for field in RAGAS_FIELDS},
    }


def build_summary(
    rows: list[dict[str, Any]],
    *,
    judge_model: str | None,
    threshold: float,
) -> dict[str, Any]:
    modes = sorted({str(row["mode"]) for row in rows})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "judge_model": judge_model,
        "faithfulness_threshold": threshold,
        "unsupported_response_definition": "Ragas faithfulness < threshold among successfully scored responses",
        "overall": _summarize_rows(rows, threshold),
        "by_mode": {
            mode: _summarize_rows([row for row in rows if row["mode"] == mode], threshold)
            for mode in modes
        },
    }


async def run_eval(args: argparse.Namespace) -> tuple[Path, Path]:
    from src.config import Settings

    settings = Settings()
    questions = load_questions(args.questions)
    output_path = args.output or (
        DEFAULT_OUTPUT_DIR / f"eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = output_path.with_suffix(".summary.json")

    answer_model = args.model or settings.openai_model
    judge_model = args.judge_model or settings.openai_model_fallback or settings.openai_model
    base_payload: dict[str, Any] = {
        "top_k": args.top_k,
        "use_hybrid": args.use_hybrid,
        "model": answer_model,
        "enable_memory": False,
        "include_contexts": True,
    }
    if args.categories:
        base_payload["categories"] = args.categories

    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout) as client:
        for item in questions:
            query = item["query"]
            row_kwargs = {"notes": item.get("notes", ""), "reference": item.get("reference", "")}
            payload = {"query": query, **base_payload}

            if not args.agentic_only:
                status, data, latency, error = await call_endpoint(client, "/api/v1/ask", payload)
                rows.append(row_from_response(query, "standard", status, latency, data, error, **row_kwargs))

            if not args.standard_only:
                status, data, latency, error = await call_endpoint(client, "/api/v1/ask-agentic", payload)
                rows.append(row_from_response(query, "agentic", status, latency, data, error, **row_kwargs))

    if args.ragas:
        await apply_ragas_scores(
            rows,
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url,
            judge_model=judge_model,
            threshold=args.faithfulness_threshold,
            timeout=args.ragas_timeout,
        )

    fieldnames = list(rows[0].keys()) if rows else []
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = build_summary(
        rows,
        judge_model=judge_model if args.ragas else None,
        threshold=args.faithfulness_threshold,
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path, summary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="调用 RAG 接口，并使用 Ragas 生成可复现的离线评测报告。")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS, help="JSONL question file")
    parser.add_argument("--output", type=Path, default=None, help="Output CSV path")
    parser.add_argument("--model", default=None, help="回答模型；默认读取 OPENAI_MODEL")
    parser.add_argument("--judge-model", default=None, help="Ragas 裁判模型；默认优先 OPENAI_MODEL_FALLBACK")
    parser.add_argument("--top-k", type=int, default=3, help="Retrieval top_k")
    parser.add_argument("--use-hybrid", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--categories", nargs="*", default=None, help="Optional arXiv category filter")
    parser.add_argument("--timeout", type=float, default=300.0, help="RAG HTTP timeout seconds")
    parser.add_argument("--ragas-timeout", type=float, default=180.0, help="单次 Ragas LLM 请求超时秒数")
    parser.add_argument("--ragas", action=argparse.BooleanOptionalAction, default=True, help="是否运行 Ragas")
    parser.add_argument(
        "--faithfulness-threshold",
        type=float,
        default=1.0,
        help="低于该 Faithfulness 分数即记为存在未受上下文支持的回答",
    )
    parser.add_argument("--standard-only", action="store_true", help="Only call /ask")
    parser.add_argument("--agentic-only", action="store_true", help="Only call /ask-agentic")
    args = parser.parse_args()
    if args.standard_only and args.agentic_only:
        parser.error("--standard-only 与 --agentic-only 不能同时使用")
    if not 0.0 <= args.faithfulness_threshold <= 1.0:
        parser.error("--faithfulness-threshold 必须在 0 到 1 之间")
    return args


def main() -> int:
    args = parse_args()
    try:
        output_path, summary_path = asyncio.run(run_eval(args))
    except (FileNotFoundError, ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Eval failed: {exc}", file=sys.stderr)
        return 1

    print(f"CSV: {output_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
