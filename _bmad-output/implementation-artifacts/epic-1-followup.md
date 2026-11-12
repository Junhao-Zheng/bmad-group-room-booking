---
title: '修补第一个史诗的跨故事反馈和验证遗漏'
type: bugfix
created: '2026-11-12'
status: in-progress
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

- [ ] 直接实现上述修补和独立断言。
- [ ] 实际执行验证，原输出及新证据放docs/evidence/epic-1-followup/；说明风险/遗漏。
- [ ] README仅补需要的新复跑说明，不编造真实组员。

## Implementation Notes

这是跨故事复盘触发的真实返工，不算第13条业务故事；不改变原12条范围。原初版和评审证据保留。

## Spec Change Log

## Review Triage Log

## Verification

- 全量Python/JS，无skip；新增认证等待/焦点、日程焦点/类型/原因、可用卡片值绑定断言。
- 真实1280×800和390×844浏览器--replay与个人历史；登录/退出、查询/创建/重放/个人记录回归；截图和指纹核对。
- 相反COOKIE_SECURE/TRUSTED_HOSTS父环境下真实verify_auth_http通过；所有数据临时隔离。
