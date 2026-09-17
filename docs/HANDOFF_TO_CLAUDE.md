# EntropyCamp / 星营：交接给 Claude

更新时间：2026-09-17，Asia/Shanghai。本次在电脑重启后重新核对程序、服务与测试，重建已丢失的交接文档。

> **2026-09-17 统一存储与修复更新（本节优先于历史描述）。**
> 分支 `feature/shared-sqlite-storage`：静态 HTTP 已禁止 private / .git / 后端源码及目录列表；
> 开机启动器优先 Zen，旧 CLI 兼容新服务，安装源脚本在 scripts/。
> 四个页面的业务数据已统一到 `~/.local/share/entropycamp/state.sqlite3`，Zen 的
> 14 卡片 / 13 历史 / 1 剪贴板 / 当前上班状态已导入，原 localStorage 未清除。
> 本轮不含自动备份、跨盘备份或备份管理 UI。参阅 [统一存储说明](SHARED_STORAGE.md)。
> 下文第 6、8、9 节关于“浏览器是业务主数据源”的描述属于历史记录，已过期。
> 之前的 3D 多节点视觉优化尚未完整验收，这一状态不因本次存储改造而改变。

> **2026-09-17 迁移已完成（由 Claude 执行）。** 程序已从
> `~/Documents/Codex/2026-08-13/hatch-pet-home-li-codex-skills/reminder-cards-prototype`
> 整体迁入 `/mnt/mydisk/My_project/Entropy/EntropyCamp`，**旧目录已删除**。
> 服务改名为 `entropycamp.service`，开机项改名为 `entropycamp.desktop` /
> `open-entropycamp-page`，旧的 `codex-reminder-cards.*` 与
> `open-reminder-cards-page` 已移除。目录现在**已经是 Git 仓库**。
> 源码内容逐字节未变，localStorage 键仍为 `lumen-reminder-*`。
> 下文凡提到旧路径、旧服务名或「不是 Git 仓库」的地方均已过期，
> 以本节为准；第 2 节的 UI 需求与第 7 节的未验收风险仍然有效。

## 1. 项目与当前结论

用户已确定英文项目名 **EntropyCamp**，中文对应 **星营**，项目标识可用 `entropycamp`。这是概念对应，不是把英文直译成“熵营”。用户希望未来逐步加入《星际拓荒》（Outer Wilds）的元素，但保留当前办公工具的全部功能。

命名意图：Entropy 呼应信息、不确定性与秩序，Camp 是任务、模型与想法汇聚的营地。

改名落地进度（2026-09-17 更新）：

- 已改：目录名（`EntropyCamp`）、systemd 服务名（`entropycamp.service`）、开机项与启动器、README 品牌展示。
- **故意未改：代码里的“提醒 / 微光 / Lumen”字样、localStorage 键（`lumen-reminder-*`）、`LUMEN_*` 环境变量、Scriptable 脚本名 `LumenToday`。** 这些改动会丢失用户既有卡片、班次与历史，或打断已安装的 iPhone 小组件；若要迁移必须显式做向后兼容，不能顺手改。

真实程序根目录：

```text
/mnt/mydisk/My_project/Entropy/EntropyCamp
```

下文将这个目录简称 `APP`。不要误去 `/home/li/.codex/visualizations/...` 或 ALFA Robot 项目。

主页：`http://127.0.0.1:8765/?variant=A`。

核心接手任务：继续完成并验收“模型恒星 / 工作对话行星 / 非工作对话彗星”的 3D 提醒关系图。

**代码已经保存；最后重写的 3D renderer 尚未进行多节点浏览器截图与完整交互验收，当前 UI 优化任务没有完成。** 最新 60 项测试通过，不代表视觉达标。以前对旧 renderer 的截图不能作为新 renderer 的验收证据。

重启后核对：2026-09-17 约 14:00，服务 active / enabled，当前 `graph-3d.js` 仍为 23776 字节、修改于 13:04；主页 JS / CSS 和测试文件也仍在原位置。本轮没有修改业务代码、重启服务、改用户数据、发飞书消息或改 Tailscale 配置。

## 2. 用户最新需求与不能丢的约束

用户要求自己截图 **Zen** 浏览器，查看真正有很多节点时的效果，不能只看只有 `Codex test` 的测试页面。

- 模型节点是太阳 / 恒星，具有恒星的颜色和风格，仍是圆形。
- 只有当前正在被使用的模型显示；历史型号不显示。
- 多个任务用同一型号时，连接同一个恒星，不能按推理等级把该型号拆成多个恒星。
- **推理等级属于具体对话 / 调用，不属于模型。** 同型号可以同时 low / max。不要在恒星上显示等级或把恒星统一染成某条对话的强度颜色。
- 等级放在对话或连线上；连接颜色最低蓝、最高红，中间分级渐变，带传输感的流动粒子。
- 连线可见当前阶段和运行时间；阶段应来自可观察事件，例如推理、工具 / 命令执行、模型输出。
- 工作中的任务是行星，尺寸克制；不同半径、不同曲率轨道、不同倾角，不在同一平面。
- 保持关注 / 不工作的对话是非常小的“被捕获彗星”，平时**完全不用显示名称**，点击后能看到即可。
- 之前状态层级要求保留：保持关注最小，工作中中等，有回复最醒目；不重要节点不应挤占主体。
- 不再是平铺一排、严格卡片网格或整体平面转盘；要有真实空间关系。
- 文字不能重叠；高密度、多型号、动态更新、窄屏都要检查。
- 点击天体弹出的详情卡要方便收起，不要一直挂着。计划支持关闭按钮、点空白、Esc、再点同节点关闭。
- 动画要平滑，但这是重复使用的办公工具，信息清晰与交互便利优先。

用户多次因“宣称优化了但实际视觉很差”提出批评。必须以实际截图和行为检查为准，不要只读代码或选最好看的一帧。

太阳系是工作信息的视觉映射，不要求真实天体物理精确。未来 Outer Wilds 主题是设计方向，不等于现在获授权复制其游戏素材或新增游戏功能。

## 3. 技术、服务与启动

原生 HTML / CSS / JavaScript + Python 标准库服务，无 React / Vite / npm 构建步骤。没有 `package.json`，不要直接按 React 项目重建。

服务入口：[run.py](../run.py)。

用户级 systemd：

```text
服务：entropycamp.service
配置：/home/li/.config/systemd/user/entropycamp.service
ExecStart：/usr/bin/python3 -B APP/run.py
WorkingDirectory：APP
```

程序现在位于第二块盘 `/mnt/mydisk`（fstab UUID 挂载，`mnt-mydisk.mount`）。
正常开机顺序下该挂载早于用户会话；unit 里放宽的重启上限
（`StartLimitBurst=20` / `RestartSec=3`）只是对挂载迟到的兜底。

本次确认服务在 13:26:19 随重启恢复，active 且 enabled。服务解释器 `/usr/bin/python3` 是 Python 3.10.12；Node v24.14.1，主要用于检查 / 回归测试。之前交互 shell 的 `python3` 是另一套 Python 3.11 环境，不要默认与 systemd 解释器相同。

```bash
cd /mnt/mydisk/My_project/Entropy/EntropyCamp
systemctl --user status entropycamp.service
systemctl --user restart entropycamp.service
journalctl --user -u entropycamp.service -n 80 --no-pager
```

- `127.0.0.1:8765`：完整主页、静态文件与私有桥接 API。
- `127.0.0.1:8003`：脱敏只读 iPhone 小组件摘要。
- 8002 是另一个已有 Life 服务，不在当前范围。
- 静态文件返回 `Cache-Control: no-store`，改 JS / CSS 后刷新即可；后端改变才需重启服务。
- 已有服务运行时不要盲目额外启动 `python3 run.py`，否则自动换主页端口或 8003 冲突；`run.py` 还会尝试打开默认浏览器。
- `启动提醒卡片.sh` 也是已有入口，不必为交接改启动机制。

~~**当前目录及父目录不是 Git 仓库。**~~ **已过期：2026-09-17 迁移时已 `git init`（分支 `main`），首个提交是迁移基线。** `private/`、`__pycache__/`、`.claude/` 已被 `.gitignore` 排除，凭据不入库。现在可以正常使用 git diff / log，但仍不要在未确认的情况下 git restore 或回滚用户改动。

## 4. 现有功能与文档入口

先读 [README.md](../README.md)，既有提醒、上班 / 下班、计数与工作时长、日报导出、历史日历与心情备注、历史对话补选、多剪贴板、天气 / 每小时短句、名钟、飞书和小组件都保留。

README 的卡片布局说明早于新 3D 图谱，不代表 renderer 现状已经完成。既有算法与部署已记录，不要复制全文或重新发明：

- [圣体钟规格](corpus-clock-twin-spec.md)
- [Big Ben 规格](big-ben-clock-spec.md)
- [Prague Orloj 规格](prague-orloj-clock-spec.md)
- [Bern Zytglogge 规格](bern-zytglogge-clock-spec.md)
- [iPhone / Funnel / SSH 部署](IPHONE_WIDGET.md)
- [圣体钟素材授权](../assets/corpus-clock/attribution.md)

**所有可读钟面统一显示北京时间 `Asia/Shanghai`。** 这是用户明确要求，不能改成英国 / 捷克时区。

| 文件，相对 APP | 职责 |
| --- | --- |
| `index.html` | 主页结构、名钟 SVG、编辑和下班反思对话框 |
| `app.js` | localStorage、工作班次 / 计数、Codex 同步、飞书 / 小组件、图谱投影和挂载 |
| `styles.css` | 主页、旧卡片和二维降级、新图谱 Canvas / 投影文字 / 详情浮层 |
| `graph-3d.js` | 最新 Three.js 恒星 / 行星 / 彗星 renderer，尚未截图验收 |
| `assets/vendor/three.module.js`, `three.core.js` | 本地 Three.js r186，必须同时存在 |
| `card-order-core.js` | 状态排序：处理 / 倒计时优先，保持关注后置 |
| `codex_monitor.py` | 本地 SQLite + rollout 增量监听，模型、effort、阶段 |
| `run.py` | HTTP API / SSE、Codex app-server、SSH 桥接、日报窗口读取 |
| `feishu_notify.py` | 飞书签名、持久化 outbox、去重与发送 |
| `work-log.html`, `work-log.js` | 当前班次对话选择、MD / JSON 日报导出 |
| `history.*`, `work-history-core.js` | 班次日历、工作时长 / 次数、心情备注、补选对话归档 |
| `clipboard.*`, `clipboard-core.js` | 多剪贴板 TXT / MD，含 Markdown 表格渲染 |
| `widget_service.py`, `scriptable/*`, `scripts/*widget*` | iPhone 只读摘要、Scriptable 与令牌脚本 |
| `test_run.py` | unittest，部分测试通过 Node 执行 JS |

## 5. 最近已写入的改动

### 5.1 推理等级归属

在 `app.js` 中：模型投影对象只有 `id / kind / label / threadCount`，**没有 effort**。对话对象独立保留 `effort / phaseLabel / phaseStartedAt / runtimeLabel / sourceLabel / modelId`。

`reasoningEffortLabel()` 将等级格式化为最低 / 低 / 中 / 高 / 很高 / 最高 / 极高。模型详情仅显示活跃对话数量；对话详情显示它自己的等级。二维后备也去除了模型的等级文字 / 等级染色，连线文字使用对应对话等级。

### 5.2 “仍在执行但旧回复未读”的模型识别

真实数据有 `codexDue=true` 与 `codexStatus=active` 同时成立。原 `graphState()` 优先返回 due，而模型筛选只找 processing，导致真正使用中的模型被隐藏。

已新增 `isGraphThreadActive()`，独立判断执行状态。模型筛选、modelId 和 effort 使用它；视觉 due 仍保留突出未读。

入口：[app.js](../app.js:3987)、`graph3DNodes()` 约 4116 行。回归测试覆盖同型号两条活动任务，其中一条未读，分别 low / max；只生成一个模型，历史 idle 型号不生成节点。

### 5.3 新太阳系 renderer

[graph-3d.js](../graph-3d.js) 最后整体重写，不能当作旧截图版本：

- 模型恒星：procedural ShaderMaterial 的暖色表面、日冕、PointLight。颜色由型号种子决定，不依赖 effort。
- 工作行星：MeshStandardMaterial + 程序生成 CanvasTexture 表面，多色系，细环显示自身 effort 颜色。
- 基础半径：恒星 0.61、processing 0.34、countdown 0.30、due 0.68、attention 0.085、idle 0.075、paused 0.065；非彗星行星有少量稳定半径变化。
- 非工作对话没有常驻名称；小彗星 / 渐暗尾迹，透明拾取球略大方便点击。
- `createOrbitSpec()` / `orbitPoint()`：不同长短轴、偏心、倾角、速度和相位，绕各自模型公转。
- 连线端点与粒子每帧跟随行星更新，不再静态连线；root 不再一直转成难读的侧视。
- 拖动改变观察角度，角度受限；滚轮缩放；相机按空间范围和 aspect 取景。
- 用屏幕投影 DOM 标签取代极小的 Sprite 文字；`placeLabels()` 贪心避让，挤不下则隐藏低优先级标签。
- 使用 delta 时间步，拖拽 / 选节点时暂停公转；reduced-motion 保留静态场景。
- dispose 清理几何、材质、纹理、观察器、事件和标签。

主要入口：`createConversationGraph()` 约 210 行，`placeLabels()` 约 410 行，`animate()` 约 457 行。纯轨道导出函数可用 Node 测试。

页面调试信号：容器 `data-graph-ready="true"`、`data-graph-node-count`、`data-graph-comet-count`、`data-selected-node`；标签 `.graph-space-label`；成功挂载 `#cardGrid.is-3d-ready`。

`mountConversationGraph()` 保留 WebGL 失败时的二维后备，不要删掉降级与可访问性。

### 5.4 详情收起

- `app.js` 详情浮层新增 ×：`data-graph-inspector-close` / `aria-label="关闭节点详情"`。
- `showGraphNodeInspector(null)` 隐藏浮层。
- 关闭按钮调用 controller.clearSelection()。
- grid 与 Canvas 有 Esc handler，点节点时聚焦 Canvas。
- renderer 点空白回调 null；再点同节点切换关闭；pointercancel 不误当点击。

代码与结构测试已写，**尚未浏览器行为验收**。新增样式在 `styles.css` 约 6236 行：`.graph-space-labels`、`.graph-space-label`、`.graph-inspector-close`。

## 6. 真实 Zen 数据与复现场景

不要把内置浏览器里的单个 `Codex test` 当成用户完整数据。Zen 与内置浏览器各自 localStorage，不共享。

**重启前只读采样**确认 Zen 有 14 条真实卡片，4 条 active 且 due，其余 10 条 idle / 不可用 / 普通提醒。四条活动任务当时都为 `gpt-5.6-sol / max`，不是多个活动型号。本次未重新读取状态，不保证这些任务重启后仍在执行。

当时样本：

| 名称 | 采样状态 |
| --- | --- |
| 运控工程师1.1 | active / outputting / max，同时 due |
| 架构 | active / reasoning / max，同时 due |
| 公司 | active / reasoning / max，同时 due |
| 小前端 | active / reasoning / max，同时 due |
| 雷达、运控1.0、测试、运控2.0、电控、视觉 | idle / xhigh |
| 闲谈 | idle，历史 gpt-6-astra / ultra，不应生成活动恒星 |
| 休息会 | 普通提醒 / unknown |
| 学校、Issac桥接 | unavailable |

另须构造隔离的 3 恒星 + 12 工作行星 + 20 彗星 + 若干已完成提醒的压力场景，各型号内部混合 low / medium / xhigh / max，查看更多元素时是否仍达标。

Zen 可执行：`/home/li/.local/bin/zen`，包装到 `/home/li/.tarball-installations/zen/zen`。

工具的 Zen localStorage 位置，本次确认目录还在：

```text
/home/li/.config/zen/1hhp8pj4.Default (release)/storage/default/http+++127.0.0.1+8765/ls/data.sqlite
```

表 `data`，字段 key / conversion_type / compression_type / value。卡片键 `lumen-reminder-cards-v1`，之前 compression_type=1，Snappy 压缩 JSON。

普通只读 SQLite 连接曾报 database locked，使用 `file:<path>?immutable=1` 成功读取，再 Snappy 解压。shell 的另一套 Python 环境当时有 snappy，系统 Python 不保证有。**这是磁盘快照，不保证包含浏览器内存最新值**；能连接真实 Zen 页面就优先通过该 origin 读取。

只读本工具数据，绝不要直接写 profile SQLite、修改用户卡片 / 上下班 / 历史，或读取其他网站 cookie、密码及不相关 storage。

## 7. 截图状态与未验收风险

之前浏览器控制列表只暴露 Edge 扩展和 Codex 内置浏览器，没有 Zen 接口，**没有成功对真实 Zen 活窗口截图**。Claude 应检查自己可用工具，尽量连接真实 Zen；或用隔离 Zen / Gecko 加载同样数据。无法做到时明确说明，不可声称已检查 Zen。

旧临时 `graph-3d-qa.html` 和 QA tab 已清理，未保存可交付截图。旧 renderer 曾暴露模型挤在一起、侧视后遮挡、标签很小的问题；这些是重写动因，不是新版验收结果。此前 viewport override 已 reset，但重启后浏览器现场应重新发现，不复用旧 tab ID / 句柄。

尚需检查的风险，不是声称全部已经复现：

1. 新 GLSL shader 在 Zen / 用户 GPU 是否正常编译，是否非空、纹理可见；第一步截图和看控制台。
2. 标签避让仅处理标签之间，尚未防止标签覆盖另一天体；密集时阶段文字可能被隐藏，要确保悬停 / 选择后仍能读所选任务的 effort / phase / runtime。
3. 天体没有屏幕投影避碰；轨道不同仍可能瞬时遮挡，应看多个时刻和视角。
4. `modelCenters()` 仍使用宽间距网格坐标，需观察是否有明显网格感，并按截图决定是否自然分布。
5. 相机取景包括外围彗星，可能让工作行星尤其在手机上过小；弱化节点不应决定主要 UI 的尺度。
6. `app.js render()` 每次销毁并重建 renderer，镜头 / 选择 / 公转时刻重置；真实 SSE 频繁变化时可能跳动、WebGL 上下文压力。先测，再针对性考虑增量更新。
7. 详情四种关闭和小彗星拾取尚未 e2e 验证。
8. 二维降级仍保留旧的大气泡 / 文字，尚未全面改为新版小彗星视觉。
9. QA 不能认领小组件主数据源、发送真实飞书消息或让假卡片覆盖公开摘要。

旧浏览器测试时有过 tab crash，原因未查明，不要武断归因于删除临时 HTML；也要检查 WebGL 重建 / 多上下文和稳定运行。

## 8. 数据、集成与安全边界

### 浏览器持久化

卡片、班次、历史、剪贴板主要保存在浏览器 localStorage，各 profile 独立。核心键见 `app.js` 头部，包含 `lumen-reminder-cards-v1`、`lumen-reminder-work-session-v1`、`lumen-reminder-work-history-v1`、`lumen-reminder-widget-source-v1`、`lumen-reminder-header-clock-v1`。剪贴板键见 `clipboard-core.js`。

改名不能顺手把这些键改掉而丢数据；如真需要迁移，显式做向后兼容。UI 测试不要点击真实上班 / 下班 / 标记已读。

### Codex 状态与日报

`codex_monitor.py` 增量读取 `CODEX_HOME/state_*.sqlite` 和 append-only rollout，模型 / effort 从元数据和 turn_context 等事件获取；阶段有 reasoning / tool / outputting / idle 等，代表可观察事件，不承诺每毫秒精确。

GET API：`/api/codex/threads`、`/api/codex/status`、`/api/codex/events`（SSE）、`/api/codex/work-log`。本地 monitor 约 0.35 秒检查；主页 60 秒后备同步 + focus / online 补查。

日报使用 `CodexWorkLogReader` 的 since / until 增量窗口与缓存，别退回读取所有历史对话。历史补选按班次时间范围和对话名称成组，不应让用户逐条消息选择。

### SSH

正确配置目标：`192.168.100.255`，用户 `tim`，远程 Codex `/home/tim/.local/bin/codex`。不是旧的 192.168.0.40 或 192.168.0.255。

配置 `APP/private/codex-remotes.json`，本次确认存在且权限 0600。使用已有 SSH 密钥、BatchMode、连接超时和 keepalive；远程低频轮询，不长期文件挂载。SSH 失败隔离于本地任务。

本次没重测 SSH，配置存在不等于当前连接可用。不要写密码、私钥或修改目标主机。

### 飞书

配置 `/home/li/.local/share/lumen-reminder/feishu.json`，队列 `/home/li/.local/share/lumen-reminder/feishu-outbox.sqlite3`，本次确认存在且 0600。

凭据不在本文；**不要打印 webhook、签名密钥或复制进交接文档**。UI 任务不应更改凭据、清理发送队列、重建机器人或发测试消息。原需求是发提醒信息，无手机打开 localhost 按钮。

### iPhone / Tailscale

部署、Scriptable 脚本、源认领与现有公网路径见 `docs/IPHONE_WIDGET.md`。`APP/private/widget/` 包含 access-token、preferred-source、sources/ 和 today.json。

只公开 8003 的脱敏摘要，不给完整 8765 开 Funnel。不要覆盖既有 8002 Life 服务 / Tailscale 配置或重新生成有效令牌。日常测试不带 `widgetSource=claim`，防止测试浏览器抢占主源。

本次未重新验公网 Funnel / iPhone 端。Scriptable 刷新受 iOS 调度，不承诺秒级及时更新。

## 9. 本次测试与 Claude 下一步

重启后实际执行：

```bash
cd /mnt/mydisk/My_project/Entropy/EntropyCamp
node --check app.js
node --check graph-3d.js
/usr/bin/python3 -m unittest -q test_run.py
```

结果：JS 检查通过，**60 tests / OK**，服务 active / enabled，`/graph-3d.js` HTTP 200 / no-store。本次没有跑浏览器截图 / 交互验收。

图谱专属 `GraphLayoutTests` 6 项，涵盖本地依赖 / 兜底、模型等级归属、未读但活动的任务映射、确定性非共面轨道与运动、关闭路径。部分仍为源码 / CSS 断言，不能代替真实浏览器行为。

建议顺序：

1. 确认 APP、服务和最新源文件，只接手这个工具；不要延续旧上下文的 Wi-Fi、卸载软件或 ALFA 操作。
2. 刷新并截图最新版，确认 WebGL / shader 正常，保存截图文件。
3. 读取真实 Zen 场景，并用隔离多型号 / 高密度 fixture 检验，避免单节点伪验收。
4. 验证点击大小天体、详情四种关闭、阶段 / effort / runtime 文字和碰撞避让。
5. 看桌面 / 窄屏、Canvas 像素非空、自动动画帧变化、拖动 / 缩放、多个时刻、连续状态更新后稳定性。
6. 按截图继续调整参数 / 布局；对频繁重建先复现、测量，再选择改法。
7. 复跑 60 项测试，清理临时测试物，不清用户数据；交付真实截图和仍有的限制。
8. 项目改名若需落地，先限定品牌展示范围；保留旧 storage 和 service 兼容，不无故搬程序目录。

可用技能：

- `diagnose`：`/home/li/.agents/skills/diagnose/SKILL.md` 或 `/home/li/.codex/skills/diagnose/SKILL.md`；用于视觉碰撞、性能 / WebGL 崩溃，先复现再修。
- `handoff`：`/home/li/.agents/skills/handoff/SKILL.md`；再次交接时使用，并把长期副本保存在项目 docs，不只放 /tmp。
- Claude 自己的浏览器 / Playwright 工具，用于隔离 fixture、截图和行为验证；不能假定 Codex 私有浏览器 API 可用。
- 当前视觉是 Three.js / shader / Canvas 原生，不需要先调用 imagegen；后续若真需 bitmap 贴图再考虑。

所有改动已在 APP，本轮无子 agent 分支、提交或遗留需要等待的测试进程。源码改动在上次交接前已落盘，这次仅恢复交接文档。

## 10. 文档保留

本次技能要求的临时文件：`/tmp/handoff-jaCP1C.md`。

长期权威副本：`APP/docs/HANDOFF_TO_CLAUDE.md`。

两份内容一致；让 Claude 优先读长期副本。`/tmp` 可能重启后清理，不再依赖它作为唯一交接记录。
