# EntropyCamp / 星营

一个无需构建、无需安装依赖的本地办公工具：提醒卡片、上下班班次与工时统计、Codex 对话关联、日报导出、历史日历、多剪贴板、每日名钟、飞书通知与 iPhone 小组件。

英文名 **EntropyCamp**，中文 **星营**。Entropy 呼应信息、不确定性与秩序，Camp 是任务、模型与想法汇聚的营地。这是概念对应，不是把英文直译成「熵营」。

## 位置与启动

程序根目录：`/mnt/mydisk/My_project/Entropy/EntropyCamp`。

开机自启由用户级 systemd 管理，登录后自动拉起服务并打开主页：

| 组件 | 路径 |
| --- | --- |
| 服务单元 | `~/.config/systemd/user/entropycamp.service` |
| 开机打开主页 | `~/.config/autostart/entropycamp.desktop` |
| 主页启动器 | `~/.local/bin/open-entropycamp-page` |

```bash
systemctl --user status entropycamp.service
systemctl --user restart entropycamp.service
journalctl --user -u entropycamp.service -n 80 --no-pager
```

也可以手动运行（服务已在跑时不要重复启动，否则会换端口或与 8003 冲突）：

```bash
python3 run.py          # 或双击 启动提醒卡片.sh
```

普通计时卡可以直接用浏览器打开 `index.html`；Codex 对话关联必须经 `run.py` 启动。

## 端口

- `127.0.0.1:8765`：完整主页、静态文件与私有桥接 API。主页 `http://127.0.0.1:8765/?variant=A`。
- `127.0.0.1:8003`：脱敏只读 iPhone 小组件摘要，需 Bearer 令牌。
- `8002` 是另一个已有 Life 服务，不属于本项目。

静态文件返回 `Cache-Control: no-store`，改 JS / CSS 后刷新即可；只有后端改动才需要重启服务。

## 数据与隐私

- 卡片、班次、历史、剪贴板保存在浏览器 localStorage，**各浏览器 profile 独立**。
- 存储键沿用 `lumen-reminder-*` 前缀（`lumen-reminder-cards-v1` 等）。**改名没有动这些键**，否则会丢失既有卡片、班次与历史；将来若要迁移必须显式做向后兼容。
- `private/` 存放小组件令牌、SSH 主机配置与小组件快照，权限 `0600`，已被 `.gitignore` 排除，不进入版本库。
- 小组件只公开 8003 的脱敏摘要，不给完整的 8765 开 Funnel。
- 日常测试打开主页请不要带 `widgetSource=claim`，否则会抢占 iPhone 小组件的主数据源。

## 功能

- 新建提醒卡片，设置标签与提醒间隔；点击整张卡片从点击时刻开始倒计时，时间到后卡片亮起，点击后熄灭并重新计时
- 已有或新建卡片可关联 Codex 对话，支持本机与已配置的 SSH 主机；远程卡片显示来源标签，SSH 断线时本机卡片不受影响
- 关联后增量监听 Codex 对话，新回复完成后实时亮起
- 上班后清零本班计数，从 `00:00:00` 记录工作时长，并统计所有已关联 Codex 对话的完成次数；下班后冻结计数与时长并暂停监听，刷新页面仍保留班次状态
- 日报记录页可选择本班关联过的 Codex 对话，导出 Markdown 或 JSON；通过追加式 rollout 文件的尾部窗口读取，只解析上班时间后的内容并缓存未变化的结果
- 历史日历记录班次、工作时长、完成次数、心情与备注，支持按班次时间范围补选历史对话
- 多剪贴板页保存多条 TXT 原文或 Markdown，支持阅读 / 源码双模式、搜索、格式筛选、复制、编辑、置顶和删除
- 页面使用实时事件连接（SSE），并在重新聚焦时补查；60 秒低频同步防止休眠漏报
- 飞书通知：提醒到期、Codex 完成、上下班等事件，带签名、持久化 outbox 与去重
- iPhone Scriptable 小组件显示上班状态、工作时长、完成次数和前四项提醒
- 左上角「每日名钟」按北京时间日期稳定轮换，也可点击右上角按钮当天手动切换

### 每日名钟

- **Corpus Clock 圣体钟**：60 齿逃逸轮每秒顺时针前进一齿，两只擒纵足交替锁止；钟面包含 60 秒槽、60 分槽、48 个小时 / 刻钟槽，并模拟 Chronophage 的摆动、眨眼、整分咬合与五分钟归准
- **Big Ben / 伊丽莎白塔**：普鲁士蓝、金色与乳白玻璃方案；时分针按真实重力擒纵每 2 秒跳进，不添加秒针；每刻钟用无声金色光波模拟 Westminster Quarters，并借用 Ayrton Light 表示上班中
- **Prague Orloj / 布拉格天文钟**：两扇哥特使徒窗、四个上盘活动人偶、偏心黄道天文盘、Mánes 式历盘与四尊下盘木雕；月相、恒星时、巴比伦不等时与旧捷克时保留布拉格天文结构
- **Bern Zytglogge / 伯尔尼时钟塔**：黑金双头指针主盘、较小的红蓝天文盘与右侧人物阁；整点前依次模拟三次雄鸡、七熊队、小丑、Chronos、金狮和塔内击钟

**所有可读钟面统一显示北京时间（`Asia/Shanghai`）**，不依赖浏览器或系统时区。

### 提醒关系图

主视图是 Three.js 的 3D 关系图：正在使用的模型是恒星，工作中的对话是绕其公转的行星，保持关注的对话是很小的被捕获彗星。推理等级属于具体对话而非模型，体现在连线与行星细环的颜色上（最低蓝、最高红）。WebGL 不可用时降级为二维列表。

> 该 renderer 尚未完成多节点浏览器截图与交互验收，详见 `docs/HANDOFF_TO_CLAUDE.md`。

## 技术

原生 HTML / CSS / JavaScript + Python 标准库服务。没有 React / Vite / npm 构建步骤，也没有 `package.json`。Node 仅用于检查与回归测试。

服务解释器是 `/usr/bin/python3`（3.10.12）；交互 shell 的 `python3` 可能是另一套 3.11 环境，不要默认两者相同。

| 文件 | 职责 |
| --- | --- |
| `index.html` | 主页结构、名钟 SVG、编辑和下班反思对话框 |
| `app.js` | localStorage、工作班次 / 计数、Codex 同步、飞书 / 小组件、图谱投影和挂载 |
| `styles.css` | 主页、旧卡片和二维降级、图谱 Canvas / 投影文字 / 详情浮层 |
| `graph-3d.js` | Three.js 恒星 / 行星 / 彗星 renderer |
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

## 测试

```bash
node --check app.js
node --check graph-3d.js
/usr/bin/python3 -m unittest -q test_run.py
```

## 文档

- [交接说明](docs/HANDOFF_TO_CLAUDE.md)
- [圣体钟规格](docs/corpus-clock-twin-spec.md)
- [Big Ben 规格](docs/big-ben-clock-spec.md)
- [Prague Orloj 规格](docs/prague-orloj-clock-spec.md)
- [Bern Zytglogge 规格](docs/bern-zytglogge-clock-spec.md)
- [iPhone / Funnel / SSH 部署](docs/IPHONE_WIDGET.md)
- [圣体钟素材授权](assets/corpus-clock/attribution.md)

## 资源来源

- `assets/corpus-clock/chronophage-*-v2.webp` 派生自 Wikimedia Commons `Chronophage pol.jpg`，原作者 Rror，授权 CC BY-SA 3.0；加工与授权信息见 `assets/corpus-clock/attribution.md`。
- 金色钟盘、波纹、擒纵齿和三圈光缝由页面程序生成，几何结构参考 Corpus Clock 专利 US8218400B2。
- `assets/corpus-clock-reference.jpg` 仅作开发期造型参考保留，当前页面不再加载整张照片。
- Big Ben 的建筑、钟面、哥特数字、分格与指针均由页面程序生成；依据见 `docs/big-ben-clock-spec.md`。
- 布拉格天文钟的立面、天文盘和人偶由页面 SVG 重建，历盘使用项目内生成的分层 SVG `assets/prague-orloj/calendar-dial-v1.svg`。
- 伯尔尼 Zytglogge 的双盘、壁画与人物机关均由页面 SVG 重建。

未来计划逐步加入《星际拓荒》（Outer Wilds）的元素作为设计方向，但保留当前办公工具的全部功能；这不等于获授权复制其游戏素材。
