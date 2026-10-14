"""Prompt, result, and artifact helpers for the human-reviewed task sync flow."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "linearUpdates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "issueId": {"type": "string"},
                    "title": {"type": "string"},
                    "reason": {"type": "string"},
                    "sourceThreadIds": {"type": "array", "items": {"type": "string"}},
                    "recommended": {"type": "boolean"},
                },
                "required": ["issueId", "title", "reason", "sourceThreadIds", "recommended"],
            },
        },
        "newLinearTasks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "reason": {"type": "string"},
                    "description": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "dueDate": {"type": ["string", "null"]},
                    "parentIssueId": {"type": ["string", "null"]},
                    "sourceThreadIds": {"type": "array", "items": {"type": "string"}},
                    "recommended": {"type": "boolean"},
                },
                "required": [
                    "title", "reason", "description", "labels", "dueDate",
                    "parentIssueId", "sourceThreadIds", "recommended",
                ],
            },
        },
        "feishuTasks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "reason": {"type": "string"},
                    "prerequisite": {"type": "string"},
                    "reportType": {"type": "string"},
                    "dueDate": {"type": ["string", "null"]},
                    "acceptance": {"type": "string"},
                    "status": {"type": "string"},
                    "sourceThreadIds": {"type": "array", "items": {"type": "string"}},
                    "recommended": {"type": "boolean"},
                },
                "required": [
                    "title", "reason", "prerequisite", "reportType", "dueDate",
                    "acceptance", "status", "sourceThreadIds", "recommended",
                ],
            },
        },
        "ignored": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"topic": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["topic", "reason"],
            },
        },
    },
    "required": ["summary", "linearUpdates", "newLinearTasks", "feishuTasks", "ignored"],
}


def _stable_id(kind: str, index: int, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{kind}-{index + 1}-{digest}"


def normalize_analysis(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Codex 没有返回结构化分析结果")
    result = {
        "summary": str(value.get("summary") or "").strip(),
        "linearUpdates": [],
        "newLinearTasks": [],
        "feishuTasks": [],
        "ignored": [],
    }
    for kind in ("linearUpdates", "newLinearTasks", "feishuTasks"):
        rows = value.get(kind)
        if not isinstance(rows, list):
            continue
        for index, raw in enumerate(rows[:100]):
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            signature = str(row.get("issueId") or row.get("title") or index)
            row["id"] = str(row.get("id") or _stable_id(kind, index, signature))
            row["selected"] = (
                bool(row.get("selected"))
                if "selected" in row
                else bool(row.get("recommended", True))
            )
            row["sourceThreadIds"] = [
                str(item) for item in row.get("sourceThreadIds", []) if str(item).strip()
            ][:50]
            result[kind].append(row)
    ignored = value.get("ignored")
    if isinstance(ignored, list):
        result["ignored"] = [dict(row) for row in ignored[:100] if isinstance(row, dict)]
    return result


def parse_analysis_text(text: str) -> dict[str, Any]:
    candidate = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    try:
        return normalize_analysis(json.loads(candidate))
    except json.JSONDecodeError as error:
        raise ValueError("Codex 分析结果不是有效 JSON") from error


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def analysis_prompt(bundle_path: Path, window_start: int, window_end: int) -> str:
    return f"""这是 EntropyCamp 发起的任务同步分析，只分析，不执行任何外部修改。

请完整读取本地文件：{bundle_path}
时间窗口（毫秒时间戳）：{window_start} 至 {window_end}。

目标：
1. 按对话和时间顺序识别已经明确对应 Linear issue 的工作推进，建议是否应追加评论。
2. 识别尚无 Linear issue、但已形成独立目标和可验收产物的工作，建议是否新建任务。
3. 识别适合由用户自行录入飞书节点表的部门任务。
4. 日常问答、电脑配置、未形成工作项的探索不要建任务。

要求：
- 这里只返回审核建议，不得创建或修改 Linear、飞书、GitHub 或文件。
- 同一主题跨多个回合应合并；Linear 评论最终执行时必须保持原对话中的事实顺序。
- 不确定 issue 编号时不要猜，改为建议新建或放入 ignored 并说明原因。
- Linear 更新项只说明为何值得更新，不必在结果里展开评论正文。
- 飞书工作内容写目的和验收，不堆实现细节。
- 严格按系统提供的 JSON Schema 输出，不要附加 Markdown。
"""


def decision_prompt(
    run_id: str,
    bundle_path: Path,
    decision_path: Path,
    revision: int,
) -> str:
    return f"""这是 EntropyCamp 任务同步批次 {run_id} 的第 {revision} 次人工确认结果。

原始对话包：{bundle_path}
人工确认文件：{decision_path}

请读取两份文件并执行确认文件中 selected=true 的项目：
- linearUpdates：依据原始对话按事实发生顺序，为对应 issue 追加一条或必要的多条评论。评论要写结论、数据、证据和边界，不要虚构完成度。
- newLinearTasks：创建选中的 Linear 任务，采用现有运控部门的命名、项目、标签和父子关系习惯；缺少关键字段时先在本对话中说明，不要猜。
- feishuTasks：不要操作飞书，只保留为用户手工录入建议。

这是人工确认后的执行阶段。未选中的项目不得执行；如果这是历史批次的修订，只应用相对已有执行记录的变化，不得重复发送相同评论或重复创建任务。完成后在本对话汇报实际成功、跳过和失败项，并给出 Linear 链接。
"""
