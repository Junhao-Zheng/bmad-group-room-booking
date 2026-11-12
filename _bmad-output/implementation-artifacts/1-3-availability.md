---
title: '按时段和人数找到可用房间'
type: feature
created: '2026-11-12'
status: done
route: dispatch
baseline_commit: ea3fba136e8b6c3cbd5bc373c167a8527376981f
story_key: 1-3-availability
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-1-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 1.3 — 按时段和人数找到可用房间

<frozen-after-approval reason="用户已授权完整实施；沿用上游基线，非额外人工批准">

## Intent

**Problem:** 成员需要按将来时段和人数找出可用房间，以便选择资源。
**Approach:** 在目录和日程基础上提供查询API与中文表单。追踪FR-06/09/10/11/22、NFR-03、ADR-02/03/06、UX-DR4/9/10。仓库 `/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking`。

## Boundaries & Constraints

**Always:** 服务端复核身份并使用同一t；时间人数规则与后续创建共用；半开相交包括booking/block；正确空结果和非法输入有区分。
**Never:** 不实施预约写入、管理取消或撤销停用；不将查询结果视为保留时段；不操作Git/远端。

## I/O & Edge-Case Matrix

|场景|输入/状态|输出/行为|错误|
|---|---|---|---|
|AC-1.3-1|未来同日30min—4h、正整数人数|GET /api/availability?start&end&attendees返回容量够、无未取消booking/block重叠的Room列表；name/location/id排序|匿名/到期401|
|AC-1.3-2|start=t、end<=start、超过t+30天、跨日、非半点、无效日期/格式|400及字段错误，严格北京YYYY-MM-DDTHH:MM；30min/4h/30天等号合法|午夜00:00跨到下一日也拒绝；禁止500|
|AC-1.3-3|0/负/小数/布尔/前导零/Unicode数字、合法>1000或上万位正整数|非法400；任意合法>1000是200空，不先转巨大int|不得绑定超SQLite范围人数|
|AC-1.3-4|10房间1000预约固定负载|10认证客户端20次预热200次测量；全部正确且零错误；nearest-rank P95<=1000ms|保存全部样本与环境；无测量不得宣称通过|

</frozen-after-approval>

## Code Map

- domain.py提供纯时间输入与预约窗口校验，输入时间严格固定长度、ASCII数字、:00/:30，无秒/时区后缀；UTC存储，Beijing同日判断，now<start<end<=now+30*86400，1800<=end-start<=14400。保留block后续可复用解析但不提前业务实现。
- 查询人数单独解析canonical ASCII正整数字符串；服务可接纯int但bool/float拒绝。超过1000先安全判断并返回空，不对超长字符串int()。JSON预约未来须用严格int解析，不能借此接受JSON数值字符串。
- services.availability(actor,start,end,attendees)：复用短只读事务、_require_actor，捕获同一个t。先验证时间/人数再查询Room；NOT EXISTS选择未取消预约与停用的半开重叠；容量与稳定排序精确合同。只返回Room，不附额外数据。
- web.py新增认证GET适配器；home.html提供start/end datetime-local(step1800)/attendees(min1 step1)有label表单，明确北京时间及查询不锁资源。现有目录/日程/登录退出保持。
- 新独立作用域availability.js，或抽取直接复用的通用查询助手，避免修改现有协议；等待/空/字段错误/失效重新登录/网络超时与条件保留清楚；textContent、20秒覆盖响应正文、finally恢复控件。
- 新tests/test_availability.py，复用合成夹具/固定Clock，不继承已有test类；测边界、容量相等、半开相邻、跨日停用、取消释放、精确DTO、超长人数与权限。
- 可复跑真实性能脚本和结果是本故事交付；准备资料在仓库外 `/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/performance_draft.py` 与 `verify_nfr_draft.py`，只借用需要的HTTP客户端/固定server/seed性能组件并核对，不能把未来尚未实现的一致性调用合入本故事脚本。固定10房间1000预约包含历史/将来/取消记录，槽必须一致；独立库独立账号，安全退出清理；200样本与20预热都保存，正确性对独立fixture预期，性能包含HTTP完整读取。

## Tasks & Acceptance

- [x] domain/services/API完成正常及拒绝路径，复用身份/只读事务/错误封装。
- [x] UI在1280x800与390x844可查询、空/错误/等待/失效清晰、无横向溢出。
- [x] 运行Python全量与JS/浏览器关键回归；实际验证新表单与旧登录退出/日程。
- [x] 运行固定负载真实HTTP性能采样并保存原始数据、环境、nearest-rank计算；README给复跑入口。

## Implementation Notes

1.2已交付精确日程DTO、半开日期与只读快照。维持业务无写接口，查询不泄漏预约私密字段。

## Spec Change Log

## Review Triage Log

|编号|裁决|处置|核对证据与理由|
|---|---|---|---|
|B1|medium|patch|禁用当前焦点控件后成功分支未恢复焦点，浏览器可退到body；成功/空结果后恢复到查询按钮，错误仍保留字段/反馈焦点。|
|B2|low|patch|三个必填控件缺required语义属实；加原生required即可，novalidate保留统一服务端中文错误。|
|B3|low|reject|与1.2相同：跨登录导航确会丢页面条件，但当前承诺是失败期间保留，不是登录草稿持久化。8h绝对会话的短时本地演示不值得新增存储/回跳机制。|
|B4|medium|patch|重复指定输出目录时先前PASS可残留；启动本轮先写INCOMPLETE并赋run_id，成功才替换最终结果，异常明确FAIL/INCOMPLETE，杜绝旧PASS冒充新结果。|
|B5|low|patch|json.loads失败会丢已知HTTP状态；解析失败保留status和异常类型/字节长度/内容hash，无需输出可能含敏感内容的原正文。|
|B6|low|patch|barrier异常在try外确会中断整批收集；移入已有异常分支即可让每个future返回错误样本并全部落盘。|
|B7|low|patch|工作负载确实只有30min，且20%人数1001走合法空结果快路；这符合已登记NFR负载但不能代表全时长最坏场景。保留原分布，加分组统计与明确局限，不另造未登记负载来替代原结果。|
|B8|medium|patch|Python bool/int及int/float相等可能掩盖JSON类型错误；exact DTO比较改为包含类型的比较，并给ok/id/capacity/total加入严格类型断言。|
|B9|medium|patch|原始样本hash不能唯一识别运行代码；环境增加真实UTC开始时间、run_id与实际应用源文件digest，并标明原始首次证据无此字段。|
|B10|low|reject|附记描述实施代理交回时的in-progress，前言当前in-review代表之后的真实流转；历史附记非当前控制字段。技能明确拒绝仅编辑本build spec的发现，不改历史事实。|
|V1|medium|patch|预验证mutation只检查前半小时仍59项过；后半小时才有booking/block的多槽查询确缺断言，补完整预期列表及相邻边界。|
|V2|medium|patch|预验证mutation只按id排序仍59项过；现有名字/地点顺序与ID同序，补反序ID/同名异地点夹具和完整DTO序列。|
|P1|low|patch|父代理检查固定fixture发现未来记录created_at及部分cancelled_at在固定now之后；虽不影响读取结果，但快照时间不真实。将合成创建/取消时刻限制<=基准时间并断言；保留初版证据，另目录复跑。|

初次实现59项Python/13项JS/浏览器/性能均通过，但首轮评审不通过。所有保留项为直接修补或定向测试；没有高/中问题延期。B4/B9属于本轮测量标识同类证据修补，其余按各自根因处理。


## Verification

- `.venv/bin/python -m unittest discover -s tests -v` 全部通过无skip。
- `node --test tests/test_*js.cjs` 已有与新查询超时回归。
- 真实浏览器桌面/手机运行新查询正常/空/错误、现有登录退出与日程。
- 独立真实HTTP性能脚本20预热+200测量，所有响应正确、零错误、P95<=1000ms，全部样本保存。

实施证据：2026-11-12 Python 全量 59 项通过，JavaScript 13 项通过；实际 Chrome 在 1280×800 和 390×844 验证新查询及旧登录/退出/日程。固定 10 房间、1000 预约、10 认证客户端的 220 个真实 HTTP 请求全部正确，最近秩 P95=13.514833ms。详见 [Story 1.3 验证记录](../../docs/evidence/story-1.3-verification.md)、[性能原始样本](../../docs/evidence/story-1.3-performance/performance-samples.jsonl)、[浏览器报告](../../docs/evidence/story-1.3-browser/browser-results.json)。故事状态保留 in-progress，等待上游评审流程。


主代理最终验收：全量66项Python、13项JavaScript通过（0 skip），详见story-1.3-final-python.txt和story-1.3-final-javascript.txt；reviewed浏览器通过。独立复算220样本、run_id、类型严格响应、样本SHA及实际源文件hash一致，P95=20.824042ms。全部保留修补项关闭，无high/medium延期。
