# WebGL 生命周期

## 原因

旧主页每次 `render()` 都用 `innerHTML` 创建新 Canvas，再创建新的 Three.js `WebGLRenderer`。Codex 阶段更新和共享数据库确认都可能触发 render；旧 controller 虽释放场景对象，却没有主动结束被替换 Canvas 的上下文。这也导致镜头、选择和公转时刻反复重置。

## 当前约束

- 主页首次渲染后复用同一个 Canvas、renderer、scene 和 camera。
- 同一帧的多个 render 请求合并为一次图谱更新。
- 标题、阶段、运行时间、推理强度等元数据原位更新，不改变 GPU 对象。
- 行星状态、`1.5×/2.25×` 大小、亮度、数据链和碎裂进度原位更新；完成状态不再触发场景重建。
- 持久行星分配变化时仅替换对应节点的模型、半径与轨道，并通过重定位或白洞喷出动画过渡。只有节点 ID 集合变化才释放旧 graph layer 后在同一上下文重建；星空、camera 和用户视角保留。
- 11 个行星、太阳和白洞 GLB 由控制器级资产库按需各加载一次；结构重建共享不可变几何与纹理，只创建实例材质。控制器销毁时统一释放资产库。
- 相机使用一个 `TrackballControls` 实例，允许连续翻转与任意方位旋转；元数据更新和结构重建都不重置用户视角。
- 场景先绘制到一个复用的 `WebGLRenderTarget`，再由一个全屏 pass 同时完成鼠标黑洞、白洞和太阳边缘光；没有逐帧创建 render target、材质或几何。
- 太阳高度图和色带由控制器级纹理库各加载一次，并与主 render target、全屏 pass 一起在 controller 销毁时释放。
- 模型读取只开放 `/assets/outer-wilds/models/<白名单>.glb`；太阳与日珥只开放 `/assets/outer-wilds/effects/<白名单文件>`。宇宙之眼、目录穿越和整个 `private/` 目录保持不可访问。
- ResizeObserver 只在 CSS 尺寸或 device pixel ratio 真实变化时重设 drawing buffer。
- `visibilitychange` 暂停 / 恢复 rAF；`pagehide` 幂等销毁 renderer 并调用 `forceContextLoss()`。BFCache 恢复时创建一个新的页面生命周期 renderer。
- 初始化或更新异常时也走相同清理，再降级到二维列表。
- 主场景 render target 使用 2× MSAA，pixel ratio 上限为 1.45；后处理只保留一个稳定缓冲，不以重复上下文换取画质。

## 回归验证

`test_graph_lifecycle.py` 覆盖：

- 200 轮、每轮两个主页 render 请求：保持 1 个 Canvas、1 个 controller，更新被按帧合并。
- 500 次元数据更新：对象身份、几何 / 纹理数量、镜头、选择和公转时刻保持。
- 60 轮节点 / 状态结构往返：旧 GPU 资源释放，资源计数回到基线。
- 隐藏页停止 rAF，恢复只产生一个循环。
- 正常销毁与初始化失败：只销毁一次、context loss 一次、观察器 / 事件 / rAF 清空。
- 自由轨迹球和屏幕空间透镜链存在，旧的根节点角度夹紧不可重新引入。

真实 WebGL 隔离测试使用 3 个模型、12 个工作节点、12 个彗星：桌面和 390×780 场景分别执行 1,000 次元数据更新与 60 次结构变化。结果均为一个上下文；资源回到 130 geometries / 13 textures / 9 programs，视角 / 选择 / 时间保留，画布像素非空。销毁后 `isContextLost()` 为 true，资源诊断归零。

正式 15 节点页面观察到自然更新计数从 4 到 6，renderer generation 始终为 1，控制台无错误。浏览器 GPU 进程显存数受其他标签、合成器与驱动池影响，不把 `nvidia-smi` 单一瞬时值作为自动通过条件；实际使用仍应观察长时间趋势是否从持续上涨变为平台。
