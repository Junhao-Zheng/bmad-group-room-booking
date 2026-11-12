# Story 3.4 独立评审与逐项裁决

三层均完成：对抗10项、边界2项、验证缺口2项。每项先独立判断，再按共同根因合并实施；第一次质量评审未零修补通过。

|来源|判定|处理|核对依据|
|---|---|---|---|
|B1|high|patch|已用隔离临时库复现：失败清理删除既有target-shm；独立评审也复现成功复制删旧WAL/journal。目标命名空间必须先拒绝已有辅助文件，包含源库恰位于目标sidecar路径，清理只处理本次创建物。|
|B2|low|reject|进程被强杀可留不完整目标，真实但只会发生在中断路径；没有成功退出或检查报告。现有恢复说明先检查完整性/schema，不能把文件存在当完成。原子发布需新增暂存/发布/清理状态，超出直接修正；本次不加，明确中断边界和新目标重试。|
|B3|low|reject|SQLite backup在外部独占锁下可持续等待。生产库WAL、短事务，正常热库已有成功证据；未约定备份完成时限。新增截止时间及策略不是直接校正，暂不加；说明可中断并解除占用后重试，不宣称有超时保证。|
|B4|low|patch|空SQLite源实测输出schema_version=0且结构检查ok；这确不能证明应用兼容。README明确CLI只证明SQLite结构一致，应用恢复必须检查schema=1并执行db.check_database，不把结构有效说成可用应用备份；不扩充通用复制工具为schema迁移器。|
|B5|medium|patch|主流程复现room.updated/before=null、target_id与after.id不同、capacity=-1仍返回DTO。增加对已证明矛盾的静态检查：action/type、创建/转换before、快照ID、正数容量等；不以当前预约窗口否定合法历史。|
|B6|medium|patch|eventShape仅检查snapshot键；嵌套对象或字符串容量可直接进入展示。补对应字段类型和可空类型检查，增加malformed值回归；没有据故障注入输入认定服务当前泄漏真实口令。|
|B7|low|reject|默认/仅日期查询需要扫描排序属实，但当前合同明确全量列表，NFR性能指标针对可用性。没有观测到此负载的失败；新增索引及schema更新是性能扩展而非直接校正，保留现有按类型日期索引和已披露无分页边界。|
|B8|medium|patch|正常查询后修改筛选时旧结果仍留在新条件下，无当前查询条件说明。按既有管理列表惯例在输入/change时使旧结果失效，提示重新查询；补真实处理器和浏览器断言。|
|B9|low|patch|新runner硬编码macOS Chrome，README又声称沿用已有runner安装方式。复用既有的显式路径优先、否则解析Playwright chromium.executablePath方式，不更改CLI公开参数；补无显式路径的解析回归。|
|B10|medium|patch|真实浏览器只核键/行数/展开文字，没有独立核实际actor/action/target/time/reason和before/after显示绑定。按API响应逐行逐单元格比较完整内容，并包含取消、撤销和更新记录。|
|E1|high|patch|与B1同根；已核源库可以恰占目标sidecar路径，因此清理有删除源库风险。保留独立发现，合并最小命名空间拒绝和不改已有文件测试。|
|E2|medium|patch|与B5中before缺失同根；当前dto允许任意action前值null，UI显示创建前。增加creation与before是否null的一致性断言。|
|V1|medium|patch|已预验证：将返回reason强制None，5项audit Python仍通过。补各实际动作原因与独立预期/存储事件一致及非null原因DOM断言；保留该mutation应被拒的证据。|
|V2|medium|patch|已预验证：before单元格改读after，14项JS仍通过。用值不同的更新/取消事件断言前后列完整值，并在真浏览器展开比较；保留mutation失败证据。|

两个评审先启动；历史pending_init占用一个并发槽，第三层两次派发未启动，在首层完成释放容量后成功新建。三层全部返回后才逐项裁决。未启动尝试不计为评审回合或传输失败。

初稿4.85MB完整差异已保留给三层；主流程逐行读完整81KB源代码/测试/交接差异，程序解析197份JSON并复算14份报告源码指纹。大量重复数据库事实未逐字人工阅读，不夸称全量人工逐字检查。

修补尚待完成及主流程复验。非人工否决，不计入decision-log。

## 修补闭环

11条patch归并8组全部完成，3条low拒绝，0defer。208项唯一Python、313项JS、真实双视口及重启/138权限检查通过；[最终核验](../story-3.4-review-fixes/parent-final-qa.json)。
