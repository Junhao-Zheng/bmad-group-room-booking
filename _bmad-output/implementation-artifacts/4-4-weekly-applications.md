---
title: 最多8周固定时段整批预约
type: feature
created: 2026-11-15
status: draft
route: dispatch
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="D-017/022/023及U-38/U-39">
## Intent

第一场7天内，每周同一时间一次，最多8周（含首场）。学生整组申请，本人导师一次批准；任一周冲突则整组暂不批准、零占用，展示冲突日期。导师本人可直接预约整组。获批后每场独立按既定规则取消。

## Boundaries & Constraints

首场结束≤当前+7天；后续场次可超7天，但每场同日半小时刻度、30分钟至4小时。后端生成场次，不相信客户端自定义日期列表。未获批不占用；批准整组原子成功/失败，已过首场开始不得跳过后补批。无无限期周期、部分批准、消息通知、批量取消整个周期或改期锁定。

## I/O & Edge-Case Matrix

|情形|结果|
|---|---|
|weeks为1/8、首场合法|准确生成1/8场（北京时间每7天），学生待审；teacher/admin直接生效需全组可用|
|weeks=0/9/bool/float/字符串|400；旧单次省略weeks等价1|
|首场超7天或任一场非法|拒绝，全组不保存半成品|
|第3周冲突（申请时或批准时）|学生申请可记录，批准时409显示冲突日期，整组待审零占用；直订整组失败零占用|
|两组交叉场次竞争批准|最多一个完整占用，另组不留下不冲突场次占用|
|同key重复/改weeks|同组同场次ID当前结果/409；失败不占成功key，学生提交已成功的待审key保留|
|取消一场/维修一场|只改变目标场；其他已批准场次仍占用|
|写第n场或审计失败|申请批准、所有预约/槽/审计全部回滚；重试不重复|

</frozen-after-approval>

## Code Map

4.2 `applications.py`、申请表及occurrences为单次骨架；`domain.py`规范化与窗口、持久payload。`booking.js`有未知响应重试，`applications.js`审批/记录。`services.py`直订与共享日程/详情已支持导师归属。先读取4.2实际合同再改，不重建第二套申请系统。

## Tasks & Acceptance

- [ ] `domain.py/applications.py`将weeks纳入规范化载荷；服务端一次生成场次，每场日期、room、人数和规则一致。审批锁内校验全部场次后写；优先构建全部冲突摘要（隐私白名单），不只报第一场导致用户误解。
- [ ] POST `/api/applications`支持1—8周及三角色：member待审，teacher/admin整批直接生效（管理员不代批别人）；现有单次直订API保持兼容，学生不得绕过。父申请/occurrence与reservation关联稳定，派生整体结果显示逐场当前状态。
- [ ] 同用户key跨直订/申请命名空间防意外碰撞与泄漏；旧已成功单次意图仍能按原入口重放。weeks省略=1与显式1等价，增加到8属于新实质意图；审批同请求重试先授权再返回首事实，不再应用新建窗口。
- [ ] `home.html/booking.js`周数选择、提交前列全部日期和整批规则；学生“申请已提交尚未占用”，导师直订“全部已生效”。查询单次只代表首场，不能说8周都空闲。审批页显示全部日期/冲突，个人页能看到每场及取消入口，导师显示正确。
- [ ] 当前严格DTO/contract-examples和后端/JS夹具同步；无未限定HTML渲染，不泄他人用途人数。身份失效与响应丢失不自动新key重提。
- [ ] 新`tests/test_weekly_applications.py`、JS及浏览器验证矩阵；真实文件库并发、失败注入、跨月/年日期、8周及第9周、每场取消、重启重放；保留其他单次测试能力。
- [ ] `docs/evidence/human-review/weekly-verification.md`保存实际证据，更新当前用户指引；勿commit/push。

**Acceptance Criteria:**
- Given8周且第3周有占用，When导师批准，Then冲突明确且一场都不生效；移除冲突后重试合法整组成功。
- Given两个交叉周期同时批准，When事务竞争，Then仅完整合法结果，无部分占用；失败审计不残留。
- Given获批8场，When学生取消其中一场并导师确认，Then仅释放该场，其他7场不变。

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

运行周期/审批/取消/重放定向Python测试、相关JS及真实浏览器8周主流程；保存源码指纹及DB断言，禁止用旧单次成功报告代替。
