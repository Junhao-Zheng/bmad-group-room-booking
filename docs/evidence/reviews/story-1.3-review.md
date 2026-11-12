# Story 1.3 独立评审与逐条裁决

三层评审全部启动后收集。edge无发现；blind为10条；verification首个上下文连续3次传输中断，不计通过，另开无上下文评审完成2条有mutation证据的发现。共4个独立评审上下文，3次传输失败，另有父代理1条fixture核对。以下均为AI裁决，不计人类否决。

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


主代理最终验收：全量66项Python、13项JavaScript通过（0 skip），详见story-1.3-final-python.txt和story-1.3-final-javascript.txt；reviewed浏览器通过。独立复算220样本、run_id、类型严格响应、样本SHA及实际源文件hash一致，P95=20.824042ms。全部保留修补项关闭，无high/medium延期。
