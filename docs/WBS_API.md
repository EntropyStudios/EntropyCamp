# 部门WBS

入口：`http://127.0.0.1:8765/wbs.html`。本页面不含AI助手，不自动发布父TASK、不评价或关闭任务，不写入Linear/飞书。

数据以Linear为准，每次以完整快照更新父级、Project、模块、负责人和状态，避免旧关系残留。模块识别为`WBS · 项目完整名称`组下的子标签。取消不表示完成。WBS默认只显示父TASK，详情展开子Issue。

“查看”可选WBS卡片或WBS关系图。关系图以项目居中、模块和任务向四周展开，项目→模块→父TASK→子Issue连线只表示归属，不是CPM前置关系。子Issue默认收起，点展开后含已完成子项，仍受人员/关键词/指定状态筛选；支持背景平移、节点单独拖动、缩放、查看全图及回到中心，节点位置和展开状态保存在浏览器。状态色与负责人姓名圆标分开，无负责人显示灰色虚线“待接取”。

当前项目、筛选、展开详情在浏览器端，不与别人共享。部门任务及手工确认的飞书对应关系存本机数据库目录内的`wbs.json`，带revision；与原提醒/任务同步状态分开。个人偏好不进入共享快照。

页面优先展示图谱：项目和视图压缩为单行，详细筛选默认折叠并提示生效条件，连接/同步信息位于内容之后。新浏览器默认关系图，已有视图偏好保留；重新进入时缩放至少 50% 以保证基本可读，进入后仍可自由缩放和查看全图。状态使用边框、底色及标签共同区分，负责人颜色独立，顶部显示当前范围内进行中/待验收/待接取父 TASK 数量，不代表验收通过率。

节点信息以任务标题为主体（大字、最多三行），负责人姓名只在右上方图例及详情显示；节点固定左侧色带表示负责人，悬停可读取姓名。负责人色使用紫/粉/冷白等独立色系，状态使用蓝/金/橙等带文字标签，未接取用灰色分段色带，避免把人员与进度混淆。

CPM 筛选只显示两端任务都可见的依赖线，并提示被隐藏的连线数量；计算仍保留完整前置，隐藏任务不等于解除依赖。飞书对账表遵守所选父 TASK 范围；未关联记录区仍是全部候选，不暗示它们属于当前 TASK。

## 更新

顶部只保留左侧返回和右侧飞书任务。登录和更新位于可折叠的“连接Linear”区域，备用AI导入收在首次配置区域。

采用Linear官方OAuth Authorization Code + PKCE(S256)，仅请求read。首次在Linear登记私有OAuth应用，回调地址为`http://127.0.0.1:8765/api/wbs/oauth/callback`，在页面填写Client ID一次；不需要Client Secret。随后点登录完成授权，后端保存访问/刷新令牌并在过期前续期。令牌仅存本机私有目录`linear-oauth.json`（0600），状态接口不返回令牌；state和HttpOnly/SameSite浏览器Cookie绑定，10分钟过期，回调日志屏蔽code。退出清除本机保存的令牌，保留数据快照；如需撤销服务端授权可在Linear应用设置解除。不要搬运WorkGraph的会话或密钥。官方说明：https://linear.app/developers/oauth-2-0-authentication。

“刷新Linear任务”完整分页后自动调用import保存本机镜像并更新页面，无需二次确认。只有保存成功才提示完成；失败明确提示仍显示旧快照。底层refresh接口仍只返回candidate和preview，import才真正保存，其他调用方不能将两者混淆。查询只读，失败保留旧快照。旧只读API密钥接口保留向后兼容但不在主页面要求填写；未登录时显示一次登录提示，不重复拼接长错误文案。AI导入仍可使用。

所有POST使用`Content-Type: application/json`及`X-Lumen-Request: 1`，接口仅接受localhost。

- GET `/api/wbs`：读取快照及revision。
- GET `/api/wbs/oauth/status`：应用登记/登录状态、用户名和回调地址，不含令牌。
- POST `/api/wbs/oauth/configure`：`{clientId:"..."}`，首次登记应用；换Client ID会清除旧登录。
- POST `/api/wbs/oauth/start`：`{}`，返回Linear授权URL并设置校验Cookie；使用127.0.0.1访问以匹配回调。完成后GET callback交换令牌并303跳回页面。
- POST `/api/wbs/oauth/logout`：`{}`，退出本机登录，不清除快照。
- GET `/api/wbs/settings`：是否配置Linear只读密钥。
- POST `/api/wbs/settings`：`{token:"...",clearToken:false}`；留空保留，明确clearToken才移除。
- POST `/api/wbs/refresh`：`{}`，读取完整候选，返回candidate和preview，不自动应用。
- POST `/api/wbs/preview`：传完整候选，返回新增/更新/移出编号和expectedRevision。
- POST `/api/wbs/import`：完整候选加`complete:true,expectedRevision:N`，保存镜像；不写Linear。
- POST `/api/wbs/link`：`{issueId:"MOTION-294",recordIds:["rec..."],note:"目的、范围、验收对应依据或已知差异",expectedRevision:N}`。只关联无parent的父TASK；空列表为解除本机关联。保留人工确认历史时间，不按名称模糊自动绑定。

完整候选格式：

```json
{
  "projects":[{"id":"Linear项目UUID","name":"项目名","url":"https://linear.app/...","state":"started","description":"项目要求"}],
  "modules":[{"name":"模块名","group":"WBS · 项目名"}],
  "issues":[{"id":"MOTION-294","title":"标题","description":"完整原文","parentId":null,"projectId":"Linear项目UUID","module":"轨迹规划","assignee":"李昊洋","status":"In Progress","statusType":"started","dueDate":null,"updatedAt":"ISO时间","blockedBy":[],"milestone":{"name":"里程碑名","targetDate":null}}],
  "complete":true,
  "expectedRevision":0
}
```

必须读取MOTION全部分页、完整description、真实父子/阻塞关系。`parentId`统一用MOTION编号；Project必须使用UUID。没项目保留null，不猜填。未完成分页不能标complete。其他团队的跨项目前置保留编号并显示待核对；不当作不存在而清掉。

## 飞书对应

复用既有`/api/performance/records?department=运控&archived=exclude&page_size=100&page=N`接口，分别查询运控和力控，按has_more完整分页并按record_id去重。通过父TASK详情手选记录并填写范围依据，可一对多；子Issue通过父TASK查对应记录。飞书详情支持`performance.html?record=rec...`并显示已关联Linear跳转。关联不表示验收已通过；状态及验收原文并排查看，状态不自动互相覆盖。只读接口暂不提供飞书网页原地址，因此跳转到本机飞书记录详情，不捏造外部表链接。未完整读到记录、空记录及缓存均明确提示。

## 依赖与时间

CPM只使用真实blockedBy，不把父子归属或Related转成前置。描述的“前置依赖”与原生关系不一致时提示，不自动造边。总览把已有子方向的跨TASK前置投影到父TASK，内部视图只计算叶子，父工期不再次累计。跨项目依赖保留并提示未完成外部前置。

只有描述中显式的`WBS 剩余工期：N 个工作日`或`WBS 预计工期：N 个工作日`用于计算，不拿estimate绩效分、截止日期差作工期。缺工期、未确认外部前置、关系不一致或循环时，依赖图仍可查看，但不显示关键路径或甘特预测。完整数据时显示相对工作日，不承诺人员资源或节假日排程。无依赖的方向保持并行，不为了图好看强制串联。

## 源码参考

已阅读内部WorkGraph仓库`nav-pppp/WorkGraph@b26afc302293c78c8cae4390a8ca0aa32a15a752`的`src/linear/pull.ts`、`src/cpm.ts`、`src/types.ts`及服务接口，参考其WBS与CPM概念。本实现按EntropyCamp的Python/原生JS架构独立编写，没有复制React/ELK实现或AI模块，也没有修改共享WorkGraph部署。
