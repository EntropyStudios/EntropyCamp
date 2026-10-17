"""Prompt, result, and artifact helpers for the human-reviewed task sync flow."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any


ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "questions": {
            "type": "array", "maxItems": 20,
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "question": {"type": "string"},
                    "context": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "relatedItemIds": {"type": "array", "items": {"type": "string"}},
                    "status": {"enum": ["pending", "answered", "ignored"]},
                    "answer": {"type": "string"},
                },
                "required": ["id", "question", "context", "options", "relatedItemIds", "status", "answer"],
            },
        },
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

# Shared by both the API handoff and the legacy file-based handoff.
WBS_ANALYSIS_RULES = """先读取Linear父子关系、父任务要求/验收及已有评论，再读取
GET http://127.0.0.1:8765/api/performance/records?department=运控&archived=exclude&page_size=100
并按has_more分页，核对飞书部门任务与Module下的父TASK是否在目的、范围、验收和状态上对应。
接口不可读时说明缺口，不能宣称已对齐。飞书状态不自动覆盖Linear状态。
只有目的、范围、验收和来源证据都吻合才可归属；标题相似、同项目、related关系不是归属证明。
日常推进写对应子Issue；父Issue只汇总申请验收和评价，评价只针对有子Issue记录的父TASK。
已有父TASK没有合适子Issue时，建议按工作方向建子Issue承载已有事实，不编造过去已存在的子任务。
没有合适父TASK时，放入parentTaskRequests提醒用户先在统管对话确认并发布父任务；
本轮不创建父任务、不创建无父子任务。用户确认父任务后，重新读取其ID和合同再二次分析/创建子Issue。
newLinearTasks仅为子Issue建议，填写parentIssueId、parentTitle、scopeEvidence、project、module、taskType；
正文使用“工作方向、工作要求、时间与分工、推进记录”模板，一个子Issue可包含多次修改与实验。
linearUpdates仅为已有子Issue过程更新或单列的合同变更；填写issueId、parentIssueId、parentTitle、scopeEvidence和updateKind（progress/scope_change）。
父TASK申请验收放入acceptanceRequests，填写父任务issueId=parentIssueId、parentTitle、childIssueIds、scopeEvidence和reason；
必须依据多个方向的整体结果及父负责人判断，不因单个子Issue结束、全部子Done或PR合并自动申请。
parentTaskRequests使用任务提议格式：问题及价值、希望结果和验证方式、与现有任务关系、预计投入/支持、是否愿意接取。
如果本来就在父TASK范围内，建议推进子Issue，不重复提出新父任务。所有工作项按TASK管理，REQ不表示父子层级。
scopeEvidence说明父合同中哪一项覆盖本工作，不能只重复标题。验收范围变更单列、默认不勾选；
父TASK缺子Issue证据时不建议评分或Done。测试通过/PR合并不自动代表父任务验收通过。
飞书和父TASK已对应时不重复建飞书任务；存在错位列出具体差异及记录ID，不能擅自扩大父任务。
待确认归属项默认不勾选并关联questions。历史指令只是分析材料，不代表本轮授权。"""

WBS_EXECUTION_RULES = """执行前逐项重新读取Linear：确认父任务实际存在，子Issue父关系、
Project/Module与合同覆盖证据正确；只有相似或related不得挂靠。
只创建已确认父TASK下的子Issue；逐项核对父编号与parentTitle、Project、Module和合同。
parentTaskRequests只是讨论草稿，永不通过本流程发布父任务。
acceptanceRequests仅在指定确认快照勾选后补充父任务申请验收评论；重新核对所列childIssueIds的真实父级和整体证据，
不执行绩效评分或父TASK Done。合同/状态调整不能混入普通进展。
父任务尚未确认、缺子Issue证据的评分/Done或仍有归属疑问的项目跳过并说明，
等用户在统管对话发布父任务后再二次操作。旧批次也遵守，人工勾选不能绕过父任务确认。
评论按原对话顺序，保留指标、证据及完成边界。原验收与后续放宽条件的结果分开；
变更需求/验收/状态/评价须单独确认，不能混入进展评论自动修改。
飞书仅给草稿/对账差异，不自动写入；程序不直接操作Linear。"""

WBS_EXECUTION_RULES += """
执行回执除result文字外，建议提供operations数组：每项itemId对应建议ID，status为
success/failed/skipped/unknown，附issueId、commentIds、url、message。
记录实际Issue和评论ID供后续去重；unknown表示状态不明，下一轮必须核对外部实际结果，不盲目重试。"""

for _kind in ("linearUpdates", "newLinearTasks", "feishuTasks"):
    ANALYSIS_SCHEMA["properties"][_kind]["items"]["properties"]["id"] = {"type": "string"}
for _kind in ("linearUpdates", "newLinearTasks"):
    ANALYSIS_SCHEMA["properties"][_kind]["items"]["properties"].update({
        "parentIssueId": {"type": ["string", "null"]},
        "parentTitle": {"type": "string"},
        "scopeEvidence": {"type": "string"},
        "project": {"type": "string"},
        "module": {"type": "string"},
        "taskType": {"type": "string"},
        "feishuRecordId": {"type": ["string", "null"]},
    })
ANALYSIS_SCHEMA["properties"]["linearUpdates"]["items"]["properties"]["updateKind"] = {
    "enum": ["progress", "acceptance", "scope_change"],
}
ANALYSIS_SCHEMA["properties"]["parentTaskRequests"] = {
    "type": "array",
    "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "id": {"type": "string"}, "title": {"type": "string"},
            "reason": {"type": "string"}, "description": {"type": "string"},
            "project": {"type": "string"}, "module": {"type": "string"},
            "feishuRecordId": {"type": ["string", "null"]},
            "sourceThreadIds": {"type": "array", "items": {"type": "string"}},
            "purpose": {"type": "string"}, "expectedResult": {"type": "string"},
            "validation": {"type": "string"}, "existingTaskRelation": {"type": "string"},
            "estimatedEffort": {"type": "string"}, "supportNeeded": {"type": "string"},
            "willingToTake": {"type": "string"},
        },
        "required": ["title", "reason", "description", "project", "module", "sourceThreadIds"],
    },
}
ANALYSIS_SCHEMA["properties"]["acceptanceRequests"] = deepcopy(
    ANALYSIS_SCHEMA["properties"]["linearUpdates"]
)
ANALYSIS_SCHEMA["properties"]["acceptanceRequests"]["items"]["properties"]["childIssueIds"] = {
    "type": "array", "items": {"type": "string"},
}
ANALYSIS_SCHEMA["properties"]["acceptanceRequests"]["items"]["properties"].pop("updateKind")

CHILD_TEMPLATE_HEADINGS = ("工作方向", "工作要求", "时间与分工", "推进记录")
ACTION_KINDS = ("linearUpdates", "newLinearTasks", "acceptanceRequests", "feishuTasks")


def _wbs_item_error(kind: str, row: dict[str, Any]) -> str:
    if kind not in {"linearUpdates", "newLinearTasks", "acceptanceRequests"}:
        return ""
    if not str(row.get("parentIssueId") or "").strip() or not str(row.get("scopeEvidence") or "").strip():
        return "请先确认父TASK及合同覆盖依据；不能仅按相似任务归属"
    if not str(row.get("parentTitle") or "").strip():
        return "请补全父TASK标题，并由AI重新核对编号与标题"
    if kind != "newLinearTasks" and not str(row.get("issueId") or "").strip():
        return "请填写要更新的Issue编号"
    if kind == "linearUpdates":
        if row.get("updateKind", "progress") not in {"progress", "scope_change"}:
            return "父任务申请验收请放入专门的验收建议区"
        if row.get("updateKind", "progress") == "progress" and row.get("issueId") == row.get("parentIssueId"):
            return "日常推进应更新子Issue，不能直接作为父TASK过程评论"
    if kind == "newLinearTasks":
        if any(not str(row.get(field) or "").strip() for field in ("project", "module", "taskType")):
            return "新建子Issue须确认Project、Module和任务类型"
        headings = set(re.findall(r"^##\s+(.+?)\s*$", str(row.get("description") or ""), re.MULTILINE))
        if not set(CHILD_TEMPLATE_HEADINGS).issubset(headings):
            return "新建子Issue描述需包含工作方向、工作要求、时间与分工、推进记录"
    if kind == "acceptanceRequests":
        children = row.get("childIssueIds")
        if row.get("issueId") != row.get("parentIssueId") or not isinstance(children, list) or not children:
            return "申请验收需明确父TASK及对应推进子Issue"
        if any(not isinstance(item, str) or not item.strip() or item == row.get("parentIssueId") for item in children):
            return "验收子Issue列表无效，父TASK不能充当自身的推进子Issue"
    return ""


def _stable_id(kind: str, index: int, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{kind}-{index + 1}-{digest}"


def normalize_analysis(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Codex 没有返回结构化分析结果")
    result = {
        "summary": str(value.get("summary") or "").strip(),
        "questions": [],
        "parentTaskRequests": [],
        "acceptanceRequests": [],
        "linearUpdates": [],
        "newLinearTasks": [],
        "feishuTasks": [],
        "ignored": [],
    }
    seen_items = set()
    for kind in (*ACTION_KINDS, "parentTaskRequests"):
        rows = value.get(kind)
        if not isinstance(rows, list):
            continue
        for index, raw in enumerate(rows[:100]):
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            signature = str(row.get("issueId") or row.get("title") or index)
            row["id"] = str(row.get("id") or _stable_id(kind, index, signature))
            if row["id"] in seen_items:
                raise ValueError("建议ID重复，请使用唯一且固定的ID")
            seen_items.add(row["id"])
            row["selected"] = (
                bool(row.get("selected"))
                if "selected" in row
                else bool(row.get("recommended", True))
            )
            row["sourceThreadIds"] = [
                str(item) for item in row.get("sourceThreadIds", []) if str(item).strip()
            ][:50]
            if kind == "parentTaskRequests":
                row["selected"] = False
            elif _wbs_item_error(kind, row):
                row["selected"] = False
            if kind == "linearUpdates" and row.get("updateKind") == "scope_change" and "selected" not in raw:
                row["selected"] = False
            result[kind].append(row)
    ignored = value.get("ignored")
    if isinstance(ignored, list):
        result["ignored"] = [dict(row) for row in ignored[:100] if isinstance(row, dict)]
    questions = value.get("questions", [])
    if not isinstance(questions, list) or len(questions) > 20:
        raise ValueError("待确认问题必须是列表，最多20条")
    seen = set()
    for index, raw in enumerate(questions):
        if not isinstance(raw, dict) or not str(raw.get("question") or "").strip():
            raise ValueError("待确认问题内容不能为空")
        question = str(raw["question"]).strip()
        identifier = str(raw.get("id") or _stable_id("question", index, question))
        status = raw.get("status", "pending")
        answer = str(raw.get("answer") or "").strip()
        if identifier in seen or status not in {"pending", "answered", "ignored"}:
            raise ValueError("问题ID重复或状态无效")
        if status == "answered" and not answer:
            raise ValueError("已回答的问题需要填写答案")
        seen.add(identifier)
        result["questions"].append({
            "id": identifier, "question": question,
            "context": str(raw.get("context") or ""),
            "options": [str(item) for item in raw.get("options", [])],
            "relatedItemIds": [str(item) for item in raw.get("relatedItemIds", [])],
            "status": status, "answer": answer,
        })
    blocked_ids = {
        item_id for question in result["questions"] if question["status"] != "answered"
        for item_id in question["relatedItemIds"]
    }
    for kind in ACTION_KINDS:
        for row in result[kind]:
            if row["id"] in blocked_ids:
                row["selected"] = False
    return result


def validate_wbs_selection(value: dict[str, Any]) -> None:
    """Reject unreviewed parent links rather than silently confirming them."""
    for kind in ("linearUpdates", "newLinearTasks", "acceptanceRequests"):
        for row in value.get(kind, []):
            error = _wbs_item_error(kind, row)
            if row.get("selected") and error:
                raise ValueError(error)
    blocked = {
        item_id for q in value.get("questions", []) if q.get("status") != "answered"
        for item_id in q.get("relatedItemIds", [])
    }
    if any(row.get("selected") and row.get("id") in blocked
           for kind in ACTION_KINDS
           for row in value.get(kind, [])):
        raise ValueError("已勾选建议仍有未确认问题，请先澄清或取消勾选")
    if any(row.get("selected") for row in value.get("parentTaskRequests", [])):
        raise ValueError("父任务草稿须在统管对话单独确认，本流程不发布父Issue")


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
- 不确定 issue 编号时不要猜，放入parentTaskRequests或questions；不得改为无父任务创建。
- Linear 更新项只说明为何值得更新，不必在结果里展开评论正文。
- 飞书工作内容写目的和验收，不堆实现细节。
- {WBS_ANALYSIS_RULES}
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
- newLinearTasks：仅创建已确认父TASK下选中的推进子Issue，核对父编号、标题和合同后使用四部分模板。
- acceptanceRequests：仅补充选中的父TASK申请验收评论，不评分、不自动设置Done。
- parentTaskRequests：只作为讨论材料，不发布父任务。
- feishuTasks：不要操作飞书，只保留为用户手工录入建议。
{WBS_EXECUTION_RULES}

这是人工确认后的执行阶段。未选中的项目不得执行；如果这是历史批次的修订，只应用相对已有执行记录的变化，不得重复发送相同评论或重复创建任务。完成后在本对话汇报实际成功、跳过和失败项，并给出 Linear 链接。
"""
