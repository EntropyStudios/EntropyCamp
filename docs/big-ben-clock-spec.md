# Big Ben / Great Clock 动态实现说明

本实现表现的是 2022 年修复后、恢复查尔斯·巴里原始维多利亚配色的伊丽莎白塔钟面。页面使用程序生成的分层 SVG，不加载带固定指针的照片。

## 视觉依据

- 钟面直径 7m，钟点数字长 60cm。
- 每面由 324 块乳白 pot-opal glass 组成；小组件中以 24 条主要径向线与 2 条同心线抽象保留玻璃结构，移动端再减半径向线，避免干扰读时。
- 分针长 4.2m、铜片制；时针长 2.7m、gun metal 制。
- 四点使用 IV，不是多数钟表采用的 IIII。
- Pugin 的 X 使用带主干、近似 F/K 轮廓的特殊字形，不画成普通交叉 X。
- 修复后的铸铁钟面框与指针为 Prussian blue，辅以金箔、钴蓝角饰、六枚圣乔治十字盾徽和乳白玻璃。
- 塔顶 Ayrton Light 原本在天黑后、议会任一院开会时亮起；应用内将其映射为“上班中”亮起。

主要来源：

- [UK Parliament — Great Clock facts](https://www.parliament.uk/about/living-heritage/building/palace/big-ben/facts-figures/great-clock-facts/)
- [UK Parliament — Turning Big Ben’s clock dials blue](https://www.parliament.uk/about/living-heritage/building/palace/big-ben/elizabeth-tower-and-big-ben-conservation-works-2017-/turning-big-bens-clock-dials-blue/)
- [UK Parliament — Facts and figures](https://www.parliament.uk/about/living-heritage/building/palace/big-ben/facts-figures/)
- [Charles Barry 1838 dial design, Public Domain](https://commons.wikimedia.org/wiki/File:Clock_Tower_dial_sketch.jpg)
- [2023 restored tower detail, CC BY 4.0](https://commons.wikimedia.org/wiki/File:Big_Ben_Elizabeth_Tower_London_2023_01_Detail.jpg)

参考照片与设计图只用于校准结构和颜色，没有直接打包进页面。

## 走时模型

Great Clock 使用 Edmund Beckett Denison 的 Double Three-legged Gravity Escapement。官方资料记录摆长 4.4m、每个 beat 为 2 秒；外部钟面没有秒针。

办公读时统一使用 `Asia/Shanghai`（北京时间），不读取浏览器或操作系统的本地时区。指针、昼夜外观和威斯敏斯特报刻都使用同一份北京时间部件，避免钟面与报时分裂。

页面将当前时间向下量化到最近的 2 秒：

    beatTime   = floor(epochMilliseconds / 2000) × 2000
    minuteDeg  = (minute + second / 60) × 6°
    hourDeg    = (hour mod 12 + minute / 60 + second / 3600) × 30°

两根指针在每个 beat 后用 165ms 的机械缓动进入新角度。角度采用最短路径展开，跨 12 点不会倒转或出现整圈跳跃。

## 报刻与办公映射

- :15、:30、:45 分别加入 1、2、3 组无声光脉冲；每组按短、短、短、长的节奏表现 Westminster Quarters。
- 整点的 4 组季度旋律从前一分钟末尾开始；Great Bell 第一击落在 `:00:00`，随后以约 4.5 秒的常规间隔按 12 小时制报时。它仍然完全静音。
- 页面默认不播放声音。
- “上班中”时 Ayrton Light 亮起；下班时熄灭。
- 中心金色花饰在每个 2 秒 beat 轻微收放，用来让小尺寸下的走时仍可察觉。
- 减少动效模式保留功能性的两秒跳针，但关闭中心收放、报刻光波、玻璃呼吸和塔灯脉冲。

## 每日名钟选择

候选钟保存在 HEADER_CLOCKS。北京时间日期使用 YYYY-MM-DD，通过稳定哈希选中当天钟表，并写入 lumen-reminder-header-clock-v1；同一天刷新结果不变，北京零点后重新选择，并尽量避免与前一天重复。

钟表右上角按钮允许当天手动切换。测试时可使用：

- ?clock=big-ben
- ?clock=corpus
- ?clockSecond=11700.05（03:15:00.05，检查刻钟光波）
- ?clockScale=1..4
- ?reduceMotion=1
