# 任务同步 API

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
