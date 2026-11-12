# Story 2.4 三层独立评审

三层全部返回后分类：blind10、edge3、verification2项预验证缺口+1项其他发现，共16条。逐条裁决后归并，均为直接条件/目标/断言/证据采集修补，不改变公开接口或业务意图；0 defer。AI裁决不计人工否决。

|编号|裁决|处置|核对证据与理由|
|---|---|---|---|
|B1|medium|patch|详情响应ID与所选ID未绑定，新增取消会按selectedId操作另条记录；以响应ID等于请求ID的直接校验及测试修补。|
|B2|medium|patch|缺失attendees/capacity先模板格式化成undefined 人，通过字符串检查；原值整数校验须在替换DOM前完成，保留原详情。|
|B3|medium|patch|HTTP200空对象被!body.ok当确定拒绝；仅有效错误信封可标api，其他走未确认分支，保留同记录手动确认。|
|B4|medium|patch|取消POST失效时expired先清空cancelFeedback再聚焦它；改为聚焦已填说明，直接修正目标。|
|B5|medium|patch|POST成功后GET401清空全部成功提示，用户失去已提交确认；仍清受保护数据，保留无记录内容的通用已取消确认和重新登录提示。|
|B6|medium|patch|禁用已聚焦取消按钮会令焦点落到body；恢复时仅在body/本次控件适当聚焦，保留其他表单焦点，真实键盘断言。|
|B7|medium|patch|pending最后一项取消后列表为空但只有通用刷新文案；复用现有空态/数量反馈逻辑，说明筛选及刷新结果。|
|B8|medium|patch|future.result首个网络/屏障异常中断证据遍历，丢剩余结果及存储；逐worker记录脱敏异常、收齐20项并写最终存储后判失败。|
|B9|medium|patch|释放后的共享日程只有独立API检查，未证明日程控件渲染；直接补真实页面房间日期查询及DOM无原预约断言。|
|B10|low|patch|20次快速真实退出不能在所有OS确定命中zombie-only分支；直接新增成功僵尸列表+PermissionError定向回归，保留活组/枚举失败拒绝。|
|E1|medium|patch|与B1相同ID绑定缺口，独立保留本条裁决后合并修补。|
|E2|medium|patch|与B3相同空/错误信封分类缺口，独立保留本条裁决后合并修补。|
|E3|medium|patch|与B2相同原值校验缺口，独立保留本条裁决后合并修补。|
|V1|medium|patch|预验证将取消后filter替换为空，34项history测试仍通过；补pending取消后带原filter查询、消失行与保留已取消详情。|
|V2|medium|patch|预验证仅移除后续GET的expired仍全过；补成功POST+GET401，断言清空/隐藏/登录说明及通用成功事实。|
|V3|medium|patch|其他发现经父流程原代码核对：模板化缺失人数绕过检查，和B2/E3同根，保留独立裁决。|

初版119项Python、71项JS及真实HTTP/双视口浏览器通过；父流程同样实际复跑119/71通过。首轮评审未通过，待修补及父流程复验。

## 修补闭环

全部16条完成修补，归并为9项直接修补任务，0 defer。实现代理定向49项history JS、8项Python及真实取消浏览器通过；主流程全量121项Python/86项JS以及新功能HTTP、历史/创建重放浏览器通过。见[最终证据](../story-2.4-review-fixes/parent-final-qa.json)。业务规则与公开接口未变；这些发现不据缺失断言直接计项目规则或ADR冲突。
