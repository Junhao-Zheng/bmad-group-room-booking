# Epic 4 查询性能复测

2026-11-15在当前schema v6代码上执行`python -m scripts.verify_availability_performance`。固定测试时钟为2026-11-12 08:00北京时间；仅测试可注入时钟，无生产HTTP改时钟入口。10间房、1000条合成预约、10个认证客户端、20次预热和200次测量；每个查询30分钟且落在当前7天窗口内。220个响应均与独立预期严格匹配，0错误；最近秩P95为16.893ms，低于1000ms门槛。

本目录保留[环境及源码哈希](performance-environment.json)、[合成数据清单](performance-fixture.json)、[汇总结果](performance-result.json)和[220条原始样本](performance-samples.jsonl)。前一次尝试沿用旧脚本的第8—10天查询，收到88个正确的7天窗口拒绝，见[旧负载失败汇总](initial-obsolete-window-result.json)；随后只调整测量脚本的查询日期范围，未修改业务校验。这个结果不覆盖4小时、长停用或生产规模的性能。
