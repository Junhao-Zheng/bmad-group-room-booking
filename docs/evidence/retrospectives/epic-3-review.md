# Epic 3 跨故事评审裁决

代码基线区间见 epic-3-git.json。三个独立镜头：adversarial 10条、edge 3条、verification-gap 2条；均已返回后统一裁决。以下保留每条来源，不将重叠发现重复计为修补任务。[15条完整评审原文](epic-3-raw-findings.json)与可见会话证据均保留；本表是父流程裁决而非原文。

|来源|发现与证据|处置|
|---|---|---|
|A1|services.create_block在创建成功、另一管理员撤销后再次提交会建立新记录；只预约有intent合同|patch文案：明确核对包含已撤销的历史；再次提交是新建，不是重放。拒绝新增停用intent协议，FR不要求。|
|A2|admin.html房间表单无method、控件初始可用，脚本失败会原生GET|patch初始禁用并在绑定完成后启用。|
|A3|rooms.js保存后未通知blocks.js，停用确认仍含旧房间标签|patch目录变更失效确认；刷新后方可重新确认，不干扰在途请求事实。|
|A4|rooms.js未知结果保留confirm=true|patch清除勾选并提示核对；保留草稿。|
|A5|admin.html未告知停用原因在共享日程可见；dto.schedule_item明确返回原因|patch标签/摘要告知所有已登录成员可见，DTO不变。|
|A6|并发全对象编辑后提交覆盖，3.1 B3已接受|accepted限制：无版本控制；保持README说明，不新增乐观锁。|
|A7|rooms.js不安全64位ID可指向相邻房间；3.1 B1曾接受|patch最小SafeInteger拒绝，撤回原“可接受不保护”判断；仍不支持完整64位UI编辑。|
|A8|services审计和管理记录fetchall，无分页已接受|accepted限制：不宣称超出当前验收负载的性能。|
|A9|backup_db遭SIGKILL可能留下未完成目标，已披露|accepted限制：成功报告才算完成；不新增原子发布。|
|A10|backup_db外部独占锁下无总截止时间，已披露|accepted限制：不保证有时限完成。|
|E1|同A2，admin.html:26—33|patch，与A2同组。|
|E2|同A7，rooms.js:119—126|patch，与A7同组。|
|E3|audit.js:19—29允许不安全整数，显示错误ID|patch拒绝不安全数字，不改变后端JSON合同。|
|V1|rooms.js/blocks.js先blocked return再保存成功事实；193项相关测试未发现|patch已确认成功与身份失效同时显示，清列表/禁用状态不恢复，补两种响应顺序。|
|V2|同A7，真实harness复现9007199254740993→9007199254740992请求|patch，与A7同组。|

15条原始发现归并8组直接修补、4项已披露限制；没有教师变更、人工否决或新的业务故事。相关原始测试193/193通过说明覆盖缺口，不能否定已复现问题。
