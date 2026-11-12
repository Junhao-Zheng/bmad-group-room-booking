# 既有历史测试启动预算校正

Y独立目录全量176项中，既有超时清理测试在1秒内尚未创建合成浏览器ready文件，失败日志为[原始全量](original-full-failure.log)。这不是撤销功能断言失败。

主流程仅将该测试的总timeout启动预算从1秒改为5秒，仍要求ready存在、发生实际TimeoutExpired、恰一注册浏览器组被清理、无关进程存活；生产runner和应用均未更改。不是保证任意主机负载下永不抖动。作为低风险测试时限机械校正，单列1次主流程阶段、0次实现代理调用；2.3经历done后返工，保留真实状态转换。

[7项定向日志](targeted-tests.log)全部通过；[合并版本192 Python/282 JS](../experiment-a-integration/parent-final-qa.json)无skip。两份失败/通过记录均保留。
