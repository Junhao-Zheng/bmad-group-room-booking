# Story 2.3 评审修复的定向验证

2026-11-12。本轮只运行覆盖所改文件的定向检查，父工作流负责全量复验。初版 `story-2.3-*` 证据保留，新证据全部在本目录。

- [个人历史 Python 测试](personal-history-tests.txt)：10 项通过。每条到期请求重置时钟，断言到达服务授权注入边界；并发修改发生在会话 SELECT 后、预约 SELECT 前；三份独立固定完整 DTO 期望覆盖未取消、本人取消、管理员取消和成对 epoch/本地时间。
- [真实 history.js 处理器](history-js-tests.txt)：17 项通过。完整 18 对详情 label/value 独立断言，开始/结束时间不同；列表快照与详情本次读取说明、手动刷新、双面板失效反馈/原失败区域焦点、非空/空成功筛选解锁后焦点恢复均覆盖。
- [运行器测试](runner-tests.txt)：3 项通过。实际独立进程组中的失败/超时子进程回收，SIGTERM 无效后的 SIGKILL 与 wait 回收，无关进程存活；已有 PASS 时 Playwright-root 缺失会生成新 run_id 的 INCOMPLETE。
- [历史专用真实浏览器](browser/browser-results.json)：1280×800、390×844 通过。真实 Tab/Enter 筛选后立即断言焦点与后续 Tab/Shift+Tab 顺序，不在提交后调用 focus 修饰结果。每种筛选同时断言页面 DOM 的编号、顺序、中文状态；保存用于实际页面渲染的响应，`source=page-rendered-response`。现有权限/错误恢复断言保留。报告保存本轮 app、driver、直接辅助脚本/夹具 SHA-256，运行前后检查一致，另含实际 Python/SQLite/包/Node/Chrome 版本。
- [真实 Chrome 清理探针](cleanup-probe.json)：Node 被 SIGKILL、Node 强制超时两条路径均无观察到的存活 Node/Chrome 进程，无关哨兵进程继续运行。[可复跑探针源文件](cleanup-probe.py)不会访问应用账号或业务数据。Chromium 自身由 Playwright 启动为独立组，私有包装器在 exec 前记录组号；因此无需依赖 Node 仍存活即可清理该次 Chromium 组。Waitress 和 Node 同样使用独立组。

支持的运行环境明确限定 macOS/Linux 的 POSIX 进程组；本次实际验证环境为 macOS、Chrome 157.0.8103.51、Playwright 1.58.2。没有宣称已在 Windows/Linux 运行这些浏览器测试。

复跑命令（应用目录）：

```bash
.venv/bin/python -m unittest tests.test_personal_history -v
node --test tests/test_history_js.cjs
.venv/bin/python -m unittest tests.test_history_browser_runner -v
.venv/bin/python -m scripts.verify_history_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir work/history-review-browser
.venv/bin/python docs/evidence/story-2.3-review-fixes/cleanup-probe.py '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
```

所有结果来自自动化与合成数据，不代表人类试用或教师验收。
