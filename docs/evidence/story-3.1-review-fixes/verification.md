# Story 3.1 定向评审修补

2026-11-12 实际执行，仅运行本次改动相关验证；全量复验由父流程负责。原始初版证据保持不变。

- `admin.html` 用 textarea 和转义 JSON 属性保存房间文本。`rooms.js` 分别保留服务器原始文本与浏览器标准化后的显示基线，使内部 LF、CR、CRLF 在无变化及仅改容量时原样提交；上游文本合同未改变。
- 容量控件解析实际数值，确认整数且位于 1—1000 才产生 JSON 数字；`1e2`、`10.0`、`01` 合法，空白、小数、越界不发 POST。
- 每个资料字段的 input/change 清除确认，重新确认前零 POST。没有自动重试。
- 管理目录手动刷新及保存后刷新遇到 AUTH_REQUIRED/FORBIDDEN 时保留身份专用指引，清空受保护目录、保留表单，保存已经成功时保留通用“资料已保存”结果；不会提示点击已禁用的刷新按钮。
- 服务错误在接受前验证 fields/conflicts 结构以及实际用于渲染的编号、人数、时间和状态。畸形结构/缺少时间进入未知结果恢复，保留输入、恢复控件。
- 浏览器失败仅保存受控阶段名、白名单错误类型、验证器自身源码行列，伴随 INCOMPLETE；不保存原 stderr、服务器异常正文、断言 actual/expected。定向回归覆盖失败报告与敏感值省略。
- 独立 SQLite 连接持有真实 BEGIN IMMEDIATE 写锁，创建与修改实际超时返回安全 503 STORE_BUSY、全表不变；释放锁后主动请求成功。测试仅将请求连接 busy_timeout 缩为 10ms，生产 15000ms 未改。UI 503 保留草稿、恢复控件，主动重试成功。
- 处理器及浏览器 DOM 精确断言相异的开始/结束时间，不能以重复开始时间通过。

实际结果：

- [18 项 Python 定向测试](python-targeted.txt)：全部通过，无 skip。
- [55 项 JavaScript 定向测试](javascript-targeted.txt)：全部通过，无 skip。
- [真实浏览器结果](browser/browser-results.json)：PASS；运行 `99fa9567a50c39554bae0e0b2983f8a5`，1280×800、390×844 均通过。[原始输出](browser-run.txt)。
- [浏览器存储](browser/runs/99fa9567a50c39554bae0e0b2983f8a5/storage.json)：10 房间、12 条审计（4 新增、8 修改）；无变化提交不增审计。原预约/槽不变，三个多行房间名称和地点逐字节等于原值。结果文件的应用及验证器源码指纹与当前文件一致。
- [桌面原始响应](browser/runs/99fa9567a50c39554bae0e0b2983f8a5/network-1280.json)、[手机原始响应](browser/runs/99fa9567a50c39554bae0e0b2983f8a5/network-390.json)含每种换行的无变化/仅容量修改结果。

```bash
.venv/bin/python -m unittest tests.test_room_management tests.test_room_management_browser_runner -v
node --test tests/test_rooms_js.cjs tests/test_room_browser_runner_js.cjs
.venv/bin/python -m scripts.verify_room_management_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir docs/evidence/story-3.1-review-fixes/browser
```
