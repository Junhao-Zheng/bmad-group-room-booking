# D-005 大组共享预约范围验证

2026-11-13。仅文档范围调整，产品代码、schema、依赖和测试套件未改。账号按user_id区分，房间占用主键为(room_id,slot_start)，不按导师组分割，故同一共享实例可支持不同导师或其负责人预约并自动拒绝重叠；无自动租户隔离。既有FR-07/08/11和ADR-03适用。

- `.venv/bin/python -m unittest tests.test_auth tests.test_create_booking -v`：48项通过，见[d005-targeted-tests.txt](d005-targeted-tests.txt)。
- `PYTHONPATH=. .venv/bin/python docs/evidence/human-review/d005-probe.py`：实际执行两个合成账号顺序预约，先201、重叠409且预约/槽/审计计数不变、相邻201。见[探针](d005-probe.py)和[结果](d005-probe.json)。该探针使用Flask测试客户端及临时库，不是真浏览器或真实人员试用；没有新增并发实验或把它计入399项JS/208项Python套件数。既有并发证据按原版本保留。

尚未设置真实账号、407容量或实际推广。普通学生是否能预约、管理员由谁担任以及共享内容可见性待用户逐项复核。用户U-08的中间选择由U-10取代；实验A冻结输入及历史开发过程不回写。
