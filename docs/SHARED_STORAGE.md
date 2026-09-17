# 统一业务存储

## 范围

卡片 / 已读与关联配置、当前班次 / 完成计数、历史班次 / 心情备注 / 对话引用、多剪贴板统一使用后端 SQLite。浏览器不再保存这些数据的权威副本。

本次不包括自动备份、跨盘备份或备份管理界面。事务与并发保护不能代替备份，也不能保证硬盘故障时恢复。

## 位置与运行

默认数据库 `~/.local/share/entropycamp/state.sqlite3`；可通过 `ENTROPYCAMP_DATA_DIR` 指定数据目录。目录 0700、数据库及 WAL / SHM 0600。使用 WAL 和 synchronous=FULL，写请求在单个事务中提交。

数据在网站根目录之外；不能通过静态 HTTP 或 Git 获取。搬程序目录不需要搬数据库；迁移到另一台电脑则必须另外迁移数据目录。不要直接复制正在写入的数据库文件作为有效迁移方式。

旧 `lumen-*` 数据键保留作为文档类型标识，不要求业务数据仍在 localStorage。天气 / 短句缓存、钟面选择、小组件源 ID 等偏好仍可按浏览器保存。

## 首次迁移

本机已从 Zen 只读导入 14 张卡片、13 条历史、1 条剪贴板和正在上班的班次。原 profile 数据未修改、未清除。

迁移脚本仅读取本工具 origin，不读取其他站点。再次运行不会覆盖已初始化的数据库：

```bash
/usr/bin/python3 scripts/import-zen-storage.py --profile '/home/li/.config/zen/1hhp8pj4.Default (release)'
```

需要 Snappy 系统库或 Python snappy 模块解码 Firefox localStorage。历史与剪贴板使用既有 core 的版本兼容逻辑；无法安全迁移时中止，不静默丢弃记录。

尚未初始化的全新数据库，可由首次打开工具的浏览器导入其旧数据。已初始化后，其他浏览器的旧数据不会覆盖它。

升级后应刷新已打开的旧版本页面；旧 JS 仍可能向原 localStorage 写入，不会自动变成新数据库写入。清理浏览器数据之前应确认使用的页面已升级。

## API 与并发

- GET `/api/state`：四种业务文档、全局 revision 和 initialized。
- GET `/api/state?revision=N`：未变化时只返回小型 unchanged 响应。
- POST `/api/state/import`：仅初始化一次，不覆盖已存在数据。
- POST `/api/state`：`updates` 按数据键包含 `base` 与 `value`，原子提交多个文档。

写请求要求 JSON、`X-Lumen-Request: 1` 和同站 Origin。HTTP Host 只接受回环本地名称，阻止 DNS rebinding Host。

不同 ID 记录 / 不同字段的编辑可三方合并；同一字段的冲突返回 409。记录删除不会擦除另一个页面的新编辑，旧班次不能冻结新班次。编辑窗口保存打开时的基线，避免后台刷新把尚未查看的内容当成用户已确认的数据。

前端每 3 秒检查 revision，聚焦时补查。保存等待服务确认；失败保留编辑内容并提示，不声称已保存。下班的历史、冻结班次和卡片状态同事务提交。飞书事件在对应业务保存成功后再入队。

## 静态文件与启动器

8765 仅提供公开前端文件以及 assets / docs 中的允许类型文件。私有目录、隐藏文件、源码、目录列表、指向私有文件的符号链接不提供，GET / HEAD 均返回 404。8003 的小组件鉴权与现有 Funnel 配置保持不变。

`scripts/open-entropycamp-page` 启动 entropycamp.service 并优先打开 Zen；系统默认浏览器不用改。`--claim-source` 仅开机项使用，旧 CLI 通过兼容脚本转到新启动器。

安装：`sh scripts/install-launchers.sh`。外部用户脚本不是仓库源文件，修改后需要重新安装。

## 验证

`/usr/bin/python3 -m unittest discover -q` 包括 HTTP 隔离、数据库重开、并发合并 / 冲突回滚、同事务下班、来源与 CSRF 检查、前端写队列 / 网络失败回滚、启动脚本模拟执行及既有功能测试。

隔离浏览器 QA：`/usr/bin/python3 scripts/serve-storage-qa.py`，使用临时目录与 8766，不读取实际 SSH / 飞书凭据。结束进程清理临时数据。正式主数据不要用于增删测试。
