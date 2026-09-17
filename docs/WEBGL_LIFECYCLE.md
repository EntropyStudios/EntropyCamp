# WebGL 生命周期

## 原因

旧主页每次 `render()` 都用 `innerHTML` 创建新 Canvas，再创建新的 Three.js `WebGLRenderer`。Codex 阶段更新和共享数据库确认都可能触发 render；旧 controller 虽释放场景对象，却没有主动结束被替换 Canvas 的上下文。这也导致镜头、选择和公转时刻反复重置。

## 当前约束

- 主页首次渲染后复用同一个 Canvas、renderer、scene 和 camera。
- 同一帧的多个 render 请求合并为一次图谱更新。
- 标题、阶段、运行时间、推理强度等元数据原位更新，不改变 GPU 对象。
- 节点 ID / 类型 / 状态 / 模型连接变化时，释放旧 graph layer 的几何、材质和纹理，再在同一上下文重建；星空、camera 和用户视角保留。
- ResizeObserver 只在 CSS 尺寸或 device pixel ratio 真实变化时重设 drawing buffer。
- `visibilitychange` 暂停 / 恢复 rAF；`pagehide` 幂等销毁 renderer 并调用 `forceContextLoss()`。BFCache 恢复时创建一个新的页面生命周期 renderer。
- 初始化或更新异常时也走相同清理，再降级到二维列表。
- 画质配置仍为 `antialias: true` 和 pixel ratio 上限 1.7；本次没有用降低画质掩盖生命周期问题。

## 回归验证

`test_graph_lifecycle.py` 覆盖：

- 200 轮、每轮两个主页 render 请求：保持 1 个 Canvas、1 个 controller，更新被按帧合并。
- 500 次元数据更新：对象身份、几何 / 纹理数量、镜头、选择和公转时刻保持。
- 60 轮节点 / 状态结构往返：旧 GPU 资源释放，资源计数回到基线。
- 隐藏页停止 rAF，恢复只产生一个循环。
- 正常销毁与初始化失败：只销毁一次、context loss 一次、观察器 / 事件 / rAF 清空。

真实 WebGL 隔离测试使用 3 个模型、12 个工作节点、12 个彗星：桌面和 390×780 场景分别执行 1,000 次元数据更新与 60 次结构变化。结果均为一个上下文；资源回到 130 geometries / 13 textures / 9 programs，视角 / 选择 / 时间保留，画布像素非空。销毁后 `isContextLost()` 为 true，资源诊断归零。

正式 15 节点页面观察到自然更新计数从 4 到 6，renderer generation 始终为 1，控制台无错误。浏览器 GPU 进程显存数受其他标签、合成器与驱动池影响，不把 `nvidia-smi` 单一瞬时值作为自动通过条件；实际使用仍应观察长时间趋势是否从持续上涨变为平台。
