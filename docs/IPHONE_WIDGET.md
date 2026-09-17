# iPhone 小组件

## 架构

```text
主页 localStorage
  -> POST 127.0.0.1:8765/api/widget/snapshot（私有、脱敏）
  -> private/widget/today.json（0600）
  -> GET 127.0.0.1:8003/api/today（Bearer，只读）
  -> Tailscale Funnel HTTPS
  -> Scriptable LumenToday
```

`8003` 仅允许：

- `GET /api/today`：必须带专用 Bearer 令牌。
- `GET /LumenToday.js`：公开脚本，不含令牌和私人数据。

其余路径和所有写请求均返回 `404`。不要把完整主页端口 `8765` 配置给 Funnel。

## 本机文件

- `private/widget/access-token`：专用令牌，权限 `0600`。
- `private/widget/today.json`：主页提交的最小摘要，权限 `0600`。
- `scriptable/LumenToday.js`：正式小组件。
- `scriptable/InstallLumenToday.js`：一次性安装器。

重新生成或确认令牌：

```bash
./scripts/generate-widget-token.py
```

脚本是幂等的，已有令牌不会被覆盖，也不会把令牌打印到日志。

## 本机验收

```bash
curl -i http://127.0.0.1:8003/api/today
curl -i -H 'Authorization: Bearer 错误令牌' http://127.0.0.1:8003/api/today
curl -i -H "Authorization: Bearer $(<private/widget/access-token)" http://127.0.0.1:8003/api/today
curl -i http://127.0.0.1:8003/api/codex/threads
```

预期依次为 `401`、`401`、`200`、`404`。

## Funnel

开启前先检查现状，避免覆盖其他配置：

```bash
tailscale status
sudo tailscale funnel status
sudo tailscale funnel --bg 8003
```

Funnel 是公网 HTTPS 入口。即使接口有高强度令牌，仍存在凭据泄露和服务漏洞风险；只有在用户明确确认后才可开启。

## iPhone 安装

1. 安装并打开一次 Scriptable。
2. 在 Scriptable 点 `+`，临时粘贴 `InstallLumenToday.js` 并运行。
3. 输入 `https://<funnel-host>/lumen/LumenToday.js`。
4. 运行安装得到的 `LumenToday`，输入 `https://<funnel-host>/lumen/api/today` 和专用令牌。
5. 预览成功后，在桌面添加 Scriptable 中号或大号小组件，Script 选择 `LumenToday`。

小组件要求 15 分钟后刷新，但实际时间由 iOS 决定，无法保证准点。断网时显示最后一次成功缓存并标注“缓存”。上班时长和普通提醒倒计时使用 iOS 原生计时文本，在小组件不重新联网的间隔内也会继续走时；点击小组件会打开一次即时联网预览。

需要把令牌送到自己的受信设备时，可在本机运行 `./scripts/copy-widget-token.sh`。它只写入桌面剪贴板，不在终端打印令牌内容。

## 当前部署

- 现有 Life 服务保留：`/` → `127.0.0.1:8002`
- 微光提醒小组件：`/lumen` → `127.0.0.1:8003`
- 正式脚本：`https://li-legion-r9000p-arx8.tailcbec8b.ts.net/lumen/LumenToday.js`
- 摘要接口：`https://li-legion-r9000p-arx8.tailcbec8b.ts.net/lumen/api/today`

## 主数据源

每个浏览器会维护独立的小组件源 ID，只有被认领的主数据源能够更新公开摘要，其他浏览器的测试页面不会覆盖它。开机启动入口已使用：

```text
http://127.0.0.1:8765/?variant=A&widgetSource=claim
```

以后如果明确改用另一个浏览器，在那个浏览器中打开一次上述地址即可切换主数据源。普通的 `?variant=A` 页面不会抢占现有主数据源。

## Codex SSH 来源

已发现并配置一个可用的 SSH Codex 主机：`192.168.100.255`（SSH 用户 `tim`，Codex 路径 `/home/tim/.local/bin/codex`）。主页的关联对话下拉框会同时显示 `本机` 和 `SSH · 192.168.100.255`。

远程线程通过本机现有 SSH 密钥以 `BatchMode`、5 秒连接超时、无交互终端方式读取。远端断线时，已存在的本机卡片继续工作；远程卡片会在下一次轮询中显示不可用，日报读取失败也会保留错误提示，不会阻塞整个主页。

远程 Codex 的完成状态使用低频轮询，不使用长期 SSH 文件挂载。若要换一台远程主机，只需在 `private/codex-remotes.json` 中增加经过确认的 SSH 别名和 `ssh-` 开头的 ID；不要把私钥、密码或令牌写入该文件。

在主页新建或编辑提醒时，Codex 下拉框会标记 `[本机]` 或 `[SSH · 192.168.100.255]`。选中远程对话后，状态轮询和日报请求会沿用该主机；SSH 暂时离线只影响远程卡片，不影响本机卡片。
