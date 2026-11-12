# Story 1.3 — 评审修复定向验证

日期：2026-11-12。初版证据文件及 `story-1.3-performance/`、`story-1.3-browser/` 目录保留原样。本轮只运行修改文件对应的定向测试、修改过的浏览器检查及要求的性能复跑；未重跑 Python/JavaScript 全量套件，全量验收由上游执行。

## 修复内容

- 可用性查询的三个必填控件补充 `required` 语义；成功及空结果在恢复控件后将焦点移回查询按钮，字段错误仍聚焦字段，网络/会话错误仍聚焦反馈。实际浏览器验证按钮获得焦点后按 Tab 可继续进入日程的会议室选择框。
- 查询测试增加第一半小时空闲、仅后续槽有预约或停用的完整结果断言，含 12:30–13:30、12:00–16:00、22:30–23:30。增加名称/地点排序与 ID 反序的精确 DTO 断言。所有成功响应明确检查 ok 为 bool、id/capacity/total 为 int，不再依赖 Python 数值宽松相等。
- 性能输出在任何准备工作之前写入新 run_id 的 INCOMPLETE；运行异常明确保留本轮 INCOMPLETE 和错误类型，旧 PASS 不会继续有效。最终 PASS 在测量、夹具检查及服务清理之后写入。环境记录真实 UTC 开始时刻、run_id、逐应用源文件 SHA-256、合并源摘要及性能脚本摘要。
- JSON 解析失败样本保留实际 HTTP 状态、异常类型、原正文的长度及 SHA-256，正文不写入证据。屏障等待位于异常收集范围内，BrokenBarrierError 同样逐个 future 返回并落盘，已提交样本不因该错误被丢弃。
- 完整 DTO 采用递归类型严格比较，拒绝 bool/int/float 替换；保留登记的查询组合，另列 SQL 筛选与人数 1001 快路径的样本数、错误数和 P95。
- 合成预约的 created_at 以及取消记录的 cancelled_at 均早于固定 now，且创建早于取消、取消早于预约开始；夹具检查增加这些时间关系断言。

## 定向验证

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| availability + performance harness Python | 17 项通过：12 个 availability 方法、5 个测量脚本验证方法 | [日志](story-1.3-reviewed-targeted-python.txt) |
| availability JavaScript | 6 项通过，包括成功/空结果按钮焦点及错误焦点保持 | [日志](story-1.3-reviewed-targeted-javascript.txt) |
| 实际浏览器 | 1280×800、390×844 全部通过；required、成功/空结果焦点和后续 Tab 检查通过 | [报告](story-1.3-browser-reviewed/browser-results.json) |

测量脚本定向失败验证包括：已有 PASS 后本轮准备工作失败；HTTP 503 且 JSON 无法解析的全部 220 个样本仍保留状态与安全摘要；全部屏障失败仍保存 220 个样本且未发起 HTTP；JSON bool/int/float 伪匹配被拒绝；违反固定时刻或创建/取消先后的夹具被拒绝。这些故障使用临时输出目录，不混入真实成功性能样本。

## Reviewed 真实 HTTP 性能

运行 ID：`a4d3484a3facd8137f902ca059954269`。真实开始时刻：`2026-11-12T06:00:19.596560+00:00`。固定业务时钟仍为北京时间 2026-11-12 08:00，种子仍为 20261112。10 房间、1000 预约（800 未取消、200 取消；500 历史、500 将来），10 个独立认证客户端，单服务进程 8 线程。

20 次预热、200 次测量全部正确，0 HTTP/解析错误、0 DTO 错误。所有 220 个样本都有当前 run_id，前后夹具槽、外键、数据库完整性及创建/取消时间关系检查通过。总体最近秩 P95：**20.824042 ms ≤ 1000 ms**。

| 登记负载分组 | 预热 | 测量 | 合计 | 测量最近秩 | 测量 P95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 执行 SQL 可用性筛选 | 16 | 160 | 176 | ceil(.95×160)=152 | 20.269958 ms |
| 人数 1001 合法空结果快路径 | 4 | 40 | 44 | ceil(.95×40)=38 | 20.824042 ms |
| 全部 | 20 | 200 | 220 | ceil(.95×200)=190 | 20.824042 ms |

查询时长全部为 30 分钟；上述快路径占 20%。本轮未改变已登记查询组合，不将混合 P95 或分组 P95 表述为 4 小时查询、长停用或任意最坏负载的性能保证。浏览器回归在独立服务上与本轮测量同时执行；结果反映本次记录环境。

完整材料：[逐请求原始样本](story-1.3-performance-reviewed/performance-samples.jsonl)、[最终结果及分组统计](story-1.3-performance-reviewed/performance-result.json)、[UTC 时刻/run_id/代码摘要/环境](story-1.3-performance-reviewed/performance-environment.json)、[固定夹具](story-1.3-performance-reviewed/performance-fixture.json)、[性能执行日志](story-1.3-performance-reviewed-run.txt)。初版证据没有当前补强的运行身份、类型严格比较及夹具时间约束；以本 reviewed 结果作为这些补强后的证据。

本次命令：

```bash
.venv/bin/python -m unittest tests.test_availability tests.test_availability_performance -v
node --test tests/test_availability_js.cjs
.venv/bin/python -m scripts.verify_auth_browser --availability --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir docs/evidence/story-1.3-browser-reviewed
.venv/bin/python -m scripts.verify_availability_performance --output-dir docs/evidence/story-1.3-performance-reviewed
```

未增加业务写接口、未操作 Git 或远端。初版文件保持原状；本轮新增证据均使用 reviewed 命名。


主代理最终验收：全量66项Python、13项JavaScript通过（0 skip），详见story-1.3-final-python.txt和story-1.3-final-javascript.txt；reviewed浏览器通过。独立复算220样本、run_id、类型严格响应、样本SHA及实际源文件hash一致，P95=20.824042ms。全部保留修补项关闭，无high/medium延期。
