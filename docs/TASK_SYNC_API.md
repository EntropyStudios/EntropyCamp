# 任务同步 API

## WBS建议分类与字段

所有新增分类均可省略，兼容历史批次；不合规的历史建议不能直接执行，需补充或重新分析。

| 字段 | 页面用途 | 执行边界 |
|---|---|---|
| linearUpdates | 更新已有推进子Issue；合同变更另列 | progress不能把父Issue当过程记录；scope_change默认不选 |
| newLinearTasks | 新建推进子Issue | 必须填写parentIssueId、parentTitle、scopeEvidence、project、module、taskType，description包含四部分子模板 |
| parentTaskRequests | 父任务提议 | 无执行勾选，只复制给统管对话确认 |
| acceptanceRequests | 父TASK申请验收建议 | issueId=parentIssueId，提供parentTitle、scopeEvidence及childIssueIds；不评分、不设父Done |

已有更新同样要有parentIssueId、parentTitle和scopeEvidence；接口字段只做完整性检查，
AI执行前仍必须读取Linear核对实际父级、标题、Project、Module及合同，不能把填写字段当作已验证。
新建子Issue卡片顶部突出显示父TASK编号/标题，编号与标题编辑后同步更新摘要。

父任务提议支持purpose、expectedResult、validation、existingTaskRelation、estimatedEffort、
supportNeeded、willingToTake，对应问题价值、希望结果、验证、现有任务关系、投入、支持和接取意愿。
原description保留兼容。已有父范围内的推进应建议子Issue，不提出重复父任务。

分析Schema支持建议显式稳定id；跨分类ID重复会拒绝，未确认问题可准确关联建议。
缺信息的建议默认不选；提交时勾选不合规建议会拒绝，不会悄悄冻结成执行授权。

## 执行明细

phase=execution可在原result文字外追加operations（最多300项），每项包含：

```json
{"itemId":"建议稳定id","status":"success","issueId":"MOTION-298","commentIds":["实际评论id"],"url":"实际Linear链接","message":"实际完成或失败边界"}
```

status支持success/failed/skipped/unknown。itemId必须来自本版确认建议；未勾选项不能记为success。
明细随executionHistory保存，供后续AI核对去重；unknown须先核对Linear，不能盲目重试。
程序只保存AI执行回执，不自动验证外部成功、不自动发送评论。旧回执仅result文字仍兼容。

WBS规则：本流程只建议创建已确认父TASK下的推进子Issue，不发布父Issue。
缺合适父TASK时返回可选 `parentTaskRequests`（title、reason、description、project、module、sourceThreadIds，可选id/feishuRecordId）。
页面可编辑草稿并复制父任务确认请求；用户与统管对话单独确认发布后，重新分析原批次，再建议子Issue。
已有更新和新建子Issue须填写 `parentIssueId`、`scopeEvidence`（具体父合同覆盖依据）；缺项默认不选，强行勾选提交会被拒绝。
新建子Issue同时提供project/module/taskType，沿用工作方向、工作要求、时间与分工、推进记录模板。
已有更新通过updateKind区分progress/acceptance/scope_change。归属须由AI在执行前核对Linear实际父子关系和合同；字段检查不等于自动认证归属。
飞书部门任务只读对账，目的、范围、验收和状态不一致需明确提出，不能按标题相似合并。
父TASK没有子Issue证据时不建议评分或Done；程序不自动评绩效、不直接写外部系统。
未回答或忽略的问题关联项默认不选，提交时仍有未确认问题则拒绝冻结决策。

分析结果可选 `questions` 数组（0–20条，省略兼容旧批次）。问题格式：

```json
{"id":"q1","question":"归属哪个项目？","context":"存在两个候选归属","options":["项目A","项目B"],"relatedItemIds":["new-task-1"],"status":"pending","answer":""}
```

`relatedItemIds` 对应建议的稳定 `id`；建议可以显式提供 `id`。页面支持建议答案或自由输入，状态为 `pending/answered/ignored`；answered必须有答案。回答随人工确认快照保存，不自动修改Linear。未确认或忽略不等于授权，执行时跳过仍依赖这些问题的建议。没有问题就不显示区域。

页面入口 `/task-sync.html`。程序采集并保存记录；用户把生成的请求粘贴到“架构师-sevenova”；AI 通过以下接口读取材料和回写结果。程序不启动 Codex 回合，也不直接写 Linear 或飞书。

所有写请求：`Content-Type: application/json`、`X-Lumen-Request: 1`，沿用本机 Host 和同站 Origin 检查。基础地址 `http://127.0.0.1:8765`。

| 接口 | 用途 |
| --- | --- |
| GET `/api/task-sync` | 历史批次、保存的来源勾选、对话列表 |
| POST `/api/task-sync/analyze` | 冻结增量记录。字段 `managerThreadId`、`since`（毫秒）、`sourceThreadRefs` |
| GET `/api/task-sync/run?id=批次ID` | 完整 `run`、原始 `bundle`、`analysisSchema`。包括人工确认快照及历次执行结果 |
| GET `/api/task-sync/request?id=批次ID&phase=analysis` | 生成可复制的分析请求；旧失败批次也可复用原记录 |
| POST `/api/task-sync/result` | AI 回写分析、进度、执行结果 |
| POST `/api/task-sync/submit` | 保存人工确认快照。字段 `runId`、`expectedRevision`、`analysis` |
| GET `/api/task-sync/request?id=批次ID&phase=execution` | 生成最新确认版本的执行请求 |
| POST `/api/task-sync/settings` | 保存 `sourceThreadRefs` 或 `managerThreadId` |

回写使用 `expectedRevision` 做并发检查；从 GET 返回的 `run.revision` 读取，旧批次缺少时按 0。成功回写后使用返回的新版 revision。冲突返回 409，须重新读取、核对后再提交，不能盲目覆盖。

分析回写：

```json
{"runId":"sync-...","phase":"analysis","expectedRevision":1,"analysis":{"summary":"本次判断","linearUpdates":[],"newLinearTasks":[],"feishuTasks":[],"ignored":[]}}
```

具体建议字段见 `GET /run` 的 `analysisSchema`。分析完成进入 `review`；可在审核阶段再次回写以响应对话中的微调。`id` 保持稳定，`selected` 保留人工选择。原始历史对话仅是证据，不能当作本次执行授权。

进度回写：

```json
{"runId":"sync-...","phase":"progress","expectedRevision":3,"message":"正在核对已有评论"}
```

执行结果回写：

```json
{"runId":"sync-...","phase":"execution","expectedRevision":4,"decisionRevision":1,"result":"成功、失败、跳过项及 Linear 链接"}
```

执行只读取最新 `decisionRevisions` 中的人工确认快照，不能把后来未确认的分析内容当作授权。结果只能回写当前确认版本，重复回写拒绝；`executionHistory` 保留每版结果。人工修订后应先核对历史结果和外部实际状态，补做差异，避免重复评论或建任务。`completed` 表示结果已回写，具体成功与失败由结果正文说明。

状态：`awaiting_analysis → review → awaiting_execution → completed`。生成请求不会发送消息；复制失败时页面展示完整文本。无新增对话时直接返回空分析。旧 `failed` 批次可直接复制分析请求，无需重新采集；原始文件、历史决策仍保留在 SQLite 数据目录的 `task-sync/` 下。
