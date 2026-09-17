# Bern Zytglogge 动态钟规格

## 产品语义

- 这是伯尔尼 Zytglogge 的办公读时适配版，不是现场仪表的远程镜像。
- 主盘、天文盘金手、日期、星期、报刻和人物机关统一使用 `Asia/Shanghai`，避免系统时区改变显示结果。
- 黄道环按恒星日运动，月针和月相保留历史天文钟的机械节奏；因此它们不应被解释为北京时间地点的天文观测值。
- 页面不声称自定的逐秒人物动作与 1530 年机构完全同速，只保证官方记载的角色、顺序和击数关系。

## 视觉结构

SVG 沿用 `1024` 宽的内部坐标，并以 `0 -48 1024 1288` 取景框给塔墙顶部与底部保留真实建筑空间；构图以伯尔尼东立面为依据：

1. 黑漆金箔主盘：外圈十二小时、内圈四刻钟，两条贯穿中心的双头杆，以及太阳脸、月牙脸、小金手和十二芒中心星；太阳脸与月牙配重具有反向补偿，随杆转动时仍保持正立。
2. 红蓝天文盘：24 小时外圈、日期环、南天投影、绕盘心旋转的偏心黄道、沿金手径向滑动并贴住黄道外缘的太阳珠、月针和月相球。
3. 五位行星神壁画：Saturn、Jupiter、Mars、Venus、Mercury。
4. 右侧人物阁只伴随下方天文盘，不跨越上方主盘；可见部分包括双铃小丑、雄鸡、Chronos 的独立沙漏手与权杖手、金狮，以及由白马指挥官/鼓手/笛手/跑者/戴冠熊/卫士组成的七熊队。
5. 石材、彩绘木雕和金箔分别使用独立材质层；所有 SVG ID 使用 `bernZytglogge` 前缀，避免同页四个内联 SVG 串用定义。

构图按完整东立面照片的水平尺度校正，而不是按单张天文盘特写猜测：上方主盘直径为下盘的 `1.229` 倍；两盘中心距为下盘直径的 `1.492` 倍。右侧人物阁石框宽、高分别为下盘直径的 `0.482` 与 `1.361` 倍，顶部高出下盘约 `0.347` 个下盘直径，底部与下盘基本齐平。人物阁与下盘外石圈在默认 `160px` 尺寸下必须保留至少 `3px` 的可见建筑间隙，不能再用几何重叠模拟实景依附关系。

背景采用圆角石质微缩立面，不是直角截图或无细节色块：外墙在默认 `160px` 尺寸下保留约 `7px` 的真实 SVG 圆角，并以同一裁切轮廓约束灰泥、墙角石、彩绘板和石缝。塔身使用连续暖灰砂岩墙，浅象牙灰上墙以交错块石收边，两扇小窗位于主盘上方中央；下方灰绿彩绘板宽度约为下盘的 `1.12` 倍，只承托天文盘，并以旧粉灰竖向彩绘柱收边。石缝、灰泥斑驳、窗台、花环、徽章、三层水平檐口和五行星壁画都必须在实际小尺寸下保留可见的明暗层级。

Hans von Thann、大钟与季度钟位于更高的塔内/塔顶机构，不属于这张紧凑东立面裁切的可见范围。运行时仍保留其击数与时间线状态，供报时联动和自动测试使用；外观不把它们缩成错误位置的装饰亭。

## 北京时间走时

设北京时间日内秒数为 `t`：

```text
mainHourAngle = t / 43200 * 360
mainMinuteAngle = (t mod 3600) / 3600 * 360
sunAngle = ((t - 43200) / 86400 * 360) mod 360
```

- 主盘小时杆十二小时一周。
- 主盘刻钟杆每小时一周，整点指顶部 `IIII`，15/30/45 分依次指 `I/II/III`。
- 天文盘金手二十四小时一周，北京 12:00 位于顶部、00:00 位于底部。
- 所有可见时间来自共享 `displayTimeParts()`，不得改回 `Date#getHours()`。

## 历史天文层

- 黄道环周期：`86164.0905 s`（恒星日），相位由 GMST 加伯尔尼经度得到的本地恒星时确定，正向顺时针运动。
- 月针周期：约 `24 h 50 min`。
- 月相周期：`29.530588853 d`。
- 日期刻度与黄道机械联动；可见日期数字仍按北京时间日界更新。
- 太阳珠不是固定半径装饰：每次更新时间都求北京时间金手射线与旋转后偏心黄道外圆的交点。
- 这些状态由绝对时间推导，不依赖 CSS 无限动画；隐藏标签页恢复时重置展开角基线，避免跨 0 度倒扫。

## 人物机关

官方资料只给顺序和大致起点，没有公开逐秒表。本实现把可调视觉时间线映射到北京时间：

1. 整点前约 210 秒，雄鸡第一次鸣叫并开喙、抬翼。
2. 七种身份明确的熊队巡游下一小时对应的 `N` 圈，小丑用独立左右臂交替敲两口小铃 `N` 次。
3. 熊队结束，雄鸡第二次鸣叫。
4. 独立季度钟在整点先敲四下；它与小丑双铃、大钟使用互不混用的脉冲。
5. Chronos 一只手翻转沙漏、另一只手举起权杖；Hans von Thann 敲大钟 `N` 下，权杖、Chronos 的嘴和金狮随每次大钟计数。
6. 大钟结束，雄鸡第三次鸣叫。
7. 非整点 `:15/:30/:45` 分别敲小钟 `1/2/3` 下。

其中 `N = hour % 12 || 12`。`prefers-reduced-motion` 或 `?reduceMotion=1` 会保留正确盘面状态，但把人物动作冻结在静止姿态。

## QA 接口

```text
?clock=bern-zytglogge
?clock=bern-zytglogge&clockDate=<ISO>
?clock=bern-zytglogge&clockDate=<ISO>&clockScale=4
?clock=bern-zytglogge&clockDate=<ISO>&reduceMotion=1
```

`window.__bernZytgloggeClockSnapshot(date)` 返回北京时间标签、盘面连续角度、偏心黄道圆心、太阳珠半径、月相和人物关节状态，用于固定时刻回归。

## 资料依据

- Bern Welcome 官方总览：https://bern.com/en/explore/tourist-attractions/attractions/zytglogge-clock-tower
- 伯尔尼市 2018 修复说明：https://www.bern.ch/mediencenter/medienmitteilungen/aktuell_ptk/sanierung-des-zytglogge-abgeschlossen
- 前钟守 Markus Marti 的天文盘说明：https://www.zytglogge-bern.ch/druckversion/astrolabium-planisphaerium-sonne-mond-tierkreis-geschichte-wochentage.php
- 人物机关顺序：https://www.zytglogge-bern.ch/druckversion/figurenspiel-ablauf-bedeutung.php
- 五组机芯说明：https://www.zytglogge-bern.ch/druckversion/uhrwerk-erbauer-gehwerk-viertelschlagwerk-stundenschlagwerk-figurenspielwerk-zeitglockenrichter.php
- 大钟与季度钟：https://www.zytglogge-bern.ch/druckversion/glockenschlag-stundenglocke-viertelstundenglocke-hans-von-thann.php
- 主盘结构：https://zytglogge-bern.ch/druckversion/zifferblaetter-ost-west.php
