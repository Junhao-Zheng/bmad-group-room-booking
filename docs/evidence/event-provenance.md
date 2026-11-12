# 状态事件与接受提交

`story-events.jsonl`中的timestamp是实际状态转换时刻，head是转换发生时已有的Git HEAD。实现和修补通常尚在工作区，故review/done可能记录相同HEAD；该字段不声称是接受后的代码版本。随后创建的完成提交保留实际顺序，不能倒填过去的时间或改写原事件。

[accepted-commits.jsonl](accepted-commits.jsonl)将每条故事的真实完成提交明确关联。最初六条是在本次复盘中回查故事卡、评审和Git而补的映射，recorded_at标示现在的记录时间，不冒充当时事件。后续完成或返工另追加关联；原证据和提交保持不变。

完成后返工记录将另存post-done-rework.jsonl，与初始build-metrics分开，避免覆盖首次评审表现。多个故事共用一次返工调用时注明共享调用ID，汇总既给唯一调用数，也说明每故事参与次数，防止重复计数。
