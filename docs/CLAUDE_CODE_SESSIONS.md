# Claude Code 会话接入

提醒主页的新建/编辑对话选择器同时列出 Codex 与本机 Claude Code；Claude 选项标注来源和项目目录名。关联后复用现有提醒、上班计数、下班对话选择、历史补选及日报导出链路。

## 数据来源

- 原生 Claude Code JSONL：`~/.claude/projects/<project>/<session UUID>.jsonl`。可用 `CLAUDE_CONFIG_DIR` 指定配置根目录。
- CloudCLI（本机 localhost:3001）实际使用这些原生日志。可选读取 `~/.cloudcli/auth.db` 的 sessions 表中 provider_session_id/custom_name 两个字段以匹配改名；只读连接，不查询登录、令牌或账号表。没有此数据库也可独立工作。
- 不读取子代理子目录，不将工具结果当用户新对话。日志不变时使用缓存；追加时从上次完整行继续读取，截断/替换后重建。缺日志返回不可用，不猜测完成。

## 兼容引用

Claude 的公开会话 ID 使用 `claude-<UUID>`，与 Codex UUID 不碰撞；hostId 仍为 local。已有 codexThreadId/hostId 字段作为通用引用沿用，不迁移或改写历史数据库。`provider=claude` 表示来源。现有 `/api/codex/threads`、status、work-log 为兼容统一入口，内部按 ID 前缀分流；Claude ID 不传给 Codex app-server 或 Codex SSE。后台约 2 秒查询已关联会话，状态通过共享 SQLite 的刷新机制显示到页面，提醒不要求主页打开。

## 回合与日报

真实 user 消息开始回合；工具结果、isMeta、内部命令与 sidechain 不开启回合。assistant 工具调用仅表示执行中。最终非错误文本带 end_turn/stop_sequence 时标记完成，使用用户消息 UUID 作为稳定回合 ID；thinking 分片即使带 end_turn 也不算完成。用户中断和 API 错误不报成功。模型来自实际日志；无推理强度字段时保持未知，不推断等级。

日报使用与 Codex 相同的班次 since/until 边界，保留在上班前开始而上班后完成的回合；下班后产生的回复不会进入该次导出。过程开关可包含公开文本过程及工具名称；不导出 thinking 内容或凭据。历史保存的是会话引用和时间范围，需要原始 JSONL 留在本机，不能恢复已删除的原始会话。

当前仅实现本机 Claude Code；未实现 SSH Claude、多用户/远程 CloudCLI、完整工具输出或附件归档。没有最终结束标记的日志不通过“静默超时”假定成功；应用崩溃时可能保持处理中，后续需另行接入运行态信号。

验证：`/usr/bin/python3 -m unittest test_claude_sessions -v`。覆盖回合归并、工具/思考分片、完成去重、部分行、文件截断、时间范围、过程过滤、中断/失败、缓存、路由隔离与后台通知计数。真实只读验证已识别 5 个 Claude 会话及会话状态/日志；未修改原生日志或自动创建提醒。
