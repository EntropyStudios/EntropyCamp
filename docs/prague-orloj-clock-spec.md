# Prague Orloj 动态钟面规格

## 目标

页面中的布拉格天文钟不是照片贴图，而是一个可读、可验证的 SVG 机械模型。它保留现存真钟的三层结构：上部使徒窗与活动人偶、中部天文盘、下部日历盘。

视觉几何以现存钟盘为准。办公读时采用北京时间适配，黄道、月球、月相、恒星时、日出日落与旧捷克时仍保留布拉格天文参考系；所有主件每分钟推进一次。

## 时间语义

- 所有用户可读时间统一使用 `Asia/Shanghai`（北京时间），不依赖浏览器或电脑时区。
- 金手和太阳标记共同映射北京时间：北京时间 12:00 朝上、00:00 朝下；钟面没有秒针。
- 十二使徒机关按北京时间 08:00–23:00 的整点触发，日历盘也在北京日期边界推进。
- 黄道、月球、月相、恒星时、布拉格日出日落、巴比伦不等时和旧捷克时仍属于历史天文层，不应当作北京时间读取。
- `?clock=prague-orloj` 可固定显示此钟；`?clockDate=<ISO 8601>` 可固定天文状态用于 QA。

## 盘面与算法

### 黄道、太阳与星时

- 布拉格位置：`50.087 N, 14.421 E`。
- Julian Date：`unixMs / 86400000 + 2440587.5`。
- 太阳黄经和赤纬采用 USNO 的低阶太阳近似。
- 地方恒星时采用 USNO GMST 公式并加布拉格经度。
- 黄道使用偏心圆：赤道半径 `190`、黄道半径 `207.5`；地方恒星时为 0 时，圆心相对盘心向左偏移 `81.8`，白羊点位于正上方。这保留了现存盘面的实测比例，而不是画成普通同心装饰环。
- 北京时间金手与太阳标记保持在同一径向线上，太阳标记落在该径向线与偏心黄道的交点。这是办公读时适配，不声称为布拉格真实太阳位置；月球和黄道仍按布拉格天文参考系运行。

### 月相

- 现存差动机构的平均朔望周期按 `29.5322986` 天模拟。
- 相位基准为 `JD 2451550.2597` 的新月。
- 月球不是固定月牙图标。SVG 根据月球相对太阳的角距实时生成亮面：新月全黑、上弦半亮、满月全亮、下弦反向半亮。

### 旧捷克时与巴比伦时

- 旧捷克时从布拉格日落开始计时；最外圈 Gothic `24` 仍随布拉格日落校正，但不再与北京时间金手共同构成历史原钟读数。
- 日出、日落使用 NOAA 太阳赤纬、时间方程和 `90.833°` 标准天顶距计算。
- 蓝色白昼区的 1–12 表示巴比伦不等时。当前白昼时段会加亮对应分区；冬夏每一“时”的实际分钟数不同。

### 日历盘

- 日历盘的石质外框与上方天文盘外框保持近似 `1:1`；小组件中允许两框轻叠约较小盘直径的 `8%`，并用哥特横梁遮住接缝。
- 下盘内部金色历盘约占外框直径的 `77%`，因此外框等大，但信息核心仍比天文盘略收敛。
- 日历盘一年旋转一周，顶部固定指针读取日期。
- `assets/prague-orloj/calendar-dial-v1.svg` 是正视分层重绘资产，保留 365 日刻线环、12 幅月令农事画章、12 幅黄道小章和矿物金底；它只负责旋转的彩绘铜盘，不包含框、玻璃、指针或人物。
- 中央布拉格三塔城门徽记、玻璃、指针和四尊木雕不随历盘旋转。观者左侧为哲学家与大天使米迦勒，右侧为天文学家与编年史家；四尊均为静态人物，不是使徒。

## 整点机关

- 北京时间 08:00–23:00 的整点触发。
- 0–3 秒：死神拉绳、侧像响应、双窗开启。
- 3–34 秒：左右两窗各六位使徒巡游。
- 34–37 秒：双窗关闭。
- 37–40 秒：金鸡动作，然后进入报时。

官方资料没有公布逐秒机械时间表，因此这 40 秒属于忠实编排，不声称逐帧复刻。角色、顺序和 08:00–23:00 的时段数值参考官方；触发时区已适配北京时间，不声称与布拉格现场同步。

## 无障碍与生命周期

- 三钟共用 `HEADER_CLOCK_RUNTIMES`，每帧只更新当前活动钟面。
- 后台标签恢复时立即重新同步，不从旧角度倒扫。
- 页面首帧继续由 `data-clock-ready=false` hydration gate 隐藏，刷新不会先闪回 Big Ben。
- `prefers-reduced-motion` 或 `?reduceMotion=1` 会保留北京时间读时位置及布拉格黄道、月球和旧捷克层状态，同时关闭使徒、鸣铃和太阳光芒装饰动画。
- `window.__pragueOrlojClockSnapshot(date)` 提供只读状态快照；DOM `data-*` 同步暴露主要角度和天文值供浏览器 QA。

## 权威依据

- [Prague City Tourism：Old Town Hall with Astronomical Clock](https://prague.eu/en/objevujte/old-town-hall-with-astronomical-clock-staromestska-radnice-s-orlojem/)
- [Orloj.eu：Astronomical dial](https://www.orloj.eu/cs/astro_cifernik.htm)
- [Orloj.eu：Main mechanism and gear ratios](https://www.orloj.eu/cs/orloj_jici.htm)
- [Orloj.eu：Old Czech 24-hour ring](https://www.orloj.eu/cs/orloj_ctyriadvacetnik.htm)
- [USNO：Approximate Solar Coordinates](https://aa.usno.navy.mil/faq/sun_approx)
- [USNO：Sidereal Time](https://aa.usno.navy.mil/faq/GAST)
- [NOAA：Solar Calculation Details](https://www.gml.noaa.gov/grad/solcalc/solareqns.PDF)
- [NASA Eclipse：Phases of the Moon](https://eclipse.gsfc.nasa.gov/phase/phasecat.html)

视觉参考为多张修复后与正面开放照片，仅用于观察形制、比例和颜色；运行时不嵌入、裁切或描摹任何照片。
