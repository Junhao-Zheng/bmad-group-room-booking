---
title: '修补第一个史诗的跨故事反馈和验证遗漏'
type: bugfix
created: '2026-11-12'
status: done
route: dispatch
baseline_commit: d545ca5ab8d339ecb037d802193ed310e0969fee
story_key: ''
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Epic 1 完成后修补

<frozen-after-approval reason="用户已授权完整完成及检查；不是新的人工验收">

## Intent

修正跨故事评审证实的登录/查询反馈和验证遗漏。影响1.1/1.2/1.3；FR02/05/06/07/22、NFR02/03、ADR05/06/08。业务规则和既有路由不变。

## Boundaries & Constraints

只做下列直接修补；不实现取消或管理命令，不改规划合同，不操作Git/远端。旧证据保留，真实新输出写独立目录。

## I/O & Edge-Case Matrix

|验收|场景|结果|
|---|---|---|
|R1|登录等待/失败|凭证不可编辑，不重复发送；完成恢复，字段错误聚焦可编辑输入|
|R2|日程键盘查询成功/空|解锁后焦点有明确位置，Tab顺序可用；必填语义明确|
|R3|日程停用及可用房间显示|完整DTO严格类型与独立值正确；DOM原因/地点/容量确实等于响应字段|
|R4|已配置HTTPS父环境或取证失败|HTTP验证仍用隔离loopback配置；浏览器先INCOMPLETE、成功后绑定源码/runner/夹具/截图及真实版本|

</frozen-after-approval>

## Code Map

- 当前auth.js只禁提交按钮。同步锁住username/password；保留提交值与可见值一致，阻止busy期间再次提交。finally解锁后聚焦服务器字段错误；超时/网络失败恢复，logout仍正常。
- schedule.js成功/空后解锁再恢复提交按钮焦点；失败沿用反馈/字段焦点。home.html日程room_id/date添加required，保留novalidate统一服务错误。login.html去掉“查询将在后续开放”，使用当前入口的稳定说明。
- test_room_schedule.py共享DTO逐字段assertIs(type(...), int/str/bool)，列表total和ok严格类型；独立断言已知停用reason值。真实浏览器同时断言对应原因文本。
- test_availability_js.cjs与verify_auth_browser.cjs对每张可用卡片断言location/capacity，至少使用id!=capacity的数据，不能只检查名字/数量或另发API代替DOM。
- verify_auth_http.py显式COOKIE_SECURE=false、TRUSTED_HOSTS=127.0.0.1；在相反父环境真实运行证明不受影响，不打印凭证。
- verify_auth_browser.py已有run_id/INCOMPLETE/独立runs；保持其先失效、失败安全、清理后PASS语义。补app、Python/JS driver及直接fixture/helper SHA256、实际Python/SQLite/依赖版本和截图SHA。采集也可能失败，置于INCOMPLETE后的try内；源文件运行前后不变才PASS。可最小共享指纹工具，避免修改不相关验证器。
- 元数据缺依赖/占用端口等失败不能留下旧PASS；补定向断言。不要改原三卡初次表现或伪造教师、人类决定。状态、完成后返工和接受提交由父流程维护。

## Tasks & Acceptance

- [x] 直接实现上述修补和独立断言。
- [x] 实际执行验证，原输出及新证据放docs/evidence/epic-1-followup/；说明风险/遗漏。
- [x] README仅补需要的新复跑说明，不编造真实组员。

## Implementation Notes

这是跨故事复盘触发的真实返工，不算第13条业务故事；不改变原12条范围。原初版和评审证据保留。

## Spec Change Log

## Review Triage Log

| 来源 | 判定 | 处置与核对依据 |
| --- | --- | --- |
| B1 | medium | patch：rooms响应及空列表确少严格envelope类型，Python相等会吞1/1.0；补独立ok/items/total断言，不改正确DTO实现。 |
| B2 | medium | patch：两个block原因相同确掩盖跨记录串值；浏览器专用夹具108采用不同原因，逐卡断言。 |
| B3 | low | reject：当前受控driver只在两视口全部断言通过后输出PASS；非零退出已拒绝，FAIL+空results须替换内部run_browser才产生。无当前正常调用者会产生该报告；增加第二套场景协议校验复杂度不属于日常缺陷直接修正。 |
| B4 | low | reject：真实driver的page.screenshot成功后才继续，异常必非零退出；任意坏字节文件须替换受控driver或外部篡改。现有SHA绑定与父流程视觉检查覆盖本轮产物；另写PNG解码和逐场景清单校验不为此低概率条件增加复杂度。 |
| B5 | low | patch：Node模块搜索可能被更近node_modules遮蔽；driver返回实际require.resolve路径/版本，launcher比较与请求安装路径一致。 |
| B6 | low | patch：增加实际Node版本、实际浏览器路径、规范化scenario与输入参数；不记录临时凭证参数。 |
| B7 | medium | patch：原mock只检查比较分支，不能发现真实hash函数漏文件；新增临时树实测app编辑/增加/删除及每个helper变化。 |
| B8 | low | patch：原调用已在验证文档说明，但JSON确未绑定父/子配置；仅记录两个无秘密配置项及child origin，并新增真实相反父环境HTTP回归。 |
| B9 | medium | patch：原超时测试字段无值/直接空payload不能证实值保留；改为实际submit处理器，验证请求和最终两字段值。 |
| B10 | medium | patch：等待时其他表单仍可输入，原成功无条件focus会打断；仅当焦点仍在本查询/反馈或body时恢复，真实双视口延迟响应保持另一表单焦点。 |
| V1 | medium | patch：预验证证明原source-change测试被缺截图错误误通过；同一含图片fixture的未变化控制必须PASS，变化必须INCOMPLETE，禁用guard后的变异实测失败。 |

## Verification

- 全量Python/JS，无skip；新增认证等待/焦点、日程焦点/类型/原因、可用卡片值绑定断言。
- 真实1280×800和390×844浏览器--replay与个人历史；登录/退出、查询/创建/重放/个人记录回归；截图和指纹核对。
- 相反COOKIE_SECURE/TRUSTED_HOSTS父环境下真实verify_auth_http通过；所有数据临时隔离。


## 本轮验证结果（独立评审前）

三次独立实现调用均传输失败且无代码产物，父流程按不可用回退直接实现一次；这不是三次完成实现。未新增业务故事或人类决定。

| 验收 | 实际通过证据 |
| --- | --- |
| R1 | test_auth_js.cjs 的响应头/正文超时、字段错误/网络失败；两视口浏览器 pending 凭证禁用、重复提交只有1请求、登录/退出及空字段聚焦 |
| R2 | test_schedule_js.cjs 成功与空结果；两视口 required、成功/空后按钮焦点与 Shift+Tab/Tab 返回 |
| R3 | test_room_schedule.py 每字段严格类型及独立原因值；可用卡片地点/容量真实DOM断言，浏览器夹具30号容量31；共享数据仍无私密字段 |
| R4 | 缺 Playwright 元数据、占用端口、运行中源码改变均 INCOMPLETE；真实相反父环境 HTTP PASS；浏览器19个app/4个验证源/30张截图哈希独立重算一致 |

106项Python与53项JavaScript均通过，无skip。真实认证/预约/重放浏览器run_id=`de4fc6552a471fdc639c04b0d06f0b98`；个人历史run_id=`fb0211b06172e9e64492de5401246931`。完整输出：[本轮证据](../../docs/evidence/epic-1-followup/)。父流程已查看390px可用房间截图，无水平溢出。

## 最终结果

108项Python、54项JavaScript及最终双视口浏览器全部通过；11条评审逐条处理，9修补、2low拒绝，无defer。详见[最终验证](../../docs/evidence/epic-1-followup/verification.md)。独立实现通道3次失败，父流程承担初次实现和评审修补2个逻辑阶段；不将父流程阶段伪称独立代理调用。
