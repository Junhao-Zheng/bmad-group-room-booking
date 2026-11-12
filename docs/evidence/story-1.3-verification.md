# Story 1.3 — 可用会议室查询验证

实施日期：2026-11-12。追踪 FR-06/09/10/11/22、NFR-03、ADR-02/03/06、UX-DR4/9/10。仅实现读取查询及共享校验；未增加预约写入、管理取消或停用撤销，也未执行 Git 或远端操作。

## 已实现行为

- `domain.py` 严格解析北京时间 `YYYY-MM-DDTHH:MM`（ASCII、00/30 分钟），共享同日/30 分钟至 4 小时/未来 30 天窗口校验。合法 30 分钟、4 小时及 30 天等号通过；start=t、跨日（含次日 00:00）、无效日期/格式以 400 字段错误拒绝。
- `query_attendees` 接受规范 URL 正整数字符串或服务纯 int，拒绝 bool/float、前导零及 Unicode 数字。大于 1000 在转巨大整数或绑定 SQLite 前归入合法空结果；单独的 `positive_integer` 保持未来 JSON 命令的严格 int 规则，不接收数字字符串。
- `services.availability` 在短只读快照事务内捕获一次 t 并重验会话；容量筛选与未取消 booking/block 占用槽的半开 `NOT EXISTS` 查询使用同一 SQL，精确返回稳定排序的 Room 列表。路由仅进行认证及一层 `{ok,data}` 包装。
- 首页新增中文时间/人数表单，包含 label、半小时时间控件、字段提示、键盘焦点、等待状态、条件保留及重新登录链接。独立 `availability.js` 只以 textContent 渲染；20 秒超时覆盖响应头及正文，finally 恢复控件，不自动重试。明确说明查询不保留时段。

## 自动化结果

| 验证 | 实际结果 | 原始证据 |
| --- | --- | --- |
| Python 全量 | 59 项通过，0 失败/跳过；新增 10 个独立 availability 测试方法及参数化边界 | [完整日志](story-1.3-python-tests.txt) |
| JavaScript | 13 项通过，0 失败/跳过；包括认证/日程回归及 availability 头/正文超时、网络错误、字段聚焦、会话失效 | [完整日志](story-1.3-javascript-tests.txt) |
| 实际浏览器 | 1280×800、390×844 全部通过，JS pageerror 为零；document.scrollWidth 分别为 1280、390 | [浏览器报告](story-1.3-browser/browser-results.json) |
| 固定负载真实 HTTP | 20 次预热 + 200 次测量，全部精确 DTO 正确，0 错误；P95 13.514833 ms ≤ 1000 ms | [性能结果](story-1.3-performance/performance-result.json) |

浏览器执行新查询的正常、无匹配、非法人数、跨日时间、等待、网络失败及真实退出后会话失效；同时实际回归旧登录/退出、日程、半开午夜、共享隐私及 HTML 文本。成功、等待及字段错误截图已通过图像查看工具检查：桌面三列输入、手机单列输入、文字和结果正常换行，没有横向截断。

截图：[桌面成功](story-1.3-browser/availability-1280.png)、[手机成功](story-1.3-browser/availability-390.png)、[桌面等待](story-1.3-browser/availability-loading-1280.png)、[手机空结果](story-1.3-browser/availability-empty-390.png)、[手机字段错误](story-1.3-browser/availability-error-390.png)。

## 性能测量与复现

固定种子 20261112；基准北京时间 2026-11-12 08:00；10 房间、1000 条预约，其中 800 条未取消、200 条取消，500 条历史、500 条将来。未取消记录的全部半小时槽完整，取消记录零槽；前后 `integrity_check`、外键及每条记录槽完整性断言通过。独立 fixture 中逐条半开区间计算预期，不调用应用查询/校验器产生预期；每次响应与完整 `{ok,data:{items,total}}` 比较，包含 Room 键、值、排序。

10 个独立账号及 cookie jar 先经真实 HTTP 登录，然后分 22 批并发 10 请求，前 2 批预热。perf_counter 从请求发送前计时直到完整响应读取及 JSON 解析完成，登录不计入。不剔除任何样本；200 次测量升序后最近秩 `ceil(0.95 × 200)=190`，取零基索引 189。预热与测量全部保存，汇总还保留排序后的 200 个耗时值及样本 SHA-256。

原始材料：[220 个逐请求样本](story-1.3-performance/performance-samples.jsonl)、[固定 fixture](story-1.3-performance/performance-fixture.json)、[环境及启动方式](story-1.3-performance/performance-environment.json)、[汇总及计算](story-1.3-performance/performance-result.json)。

环境为 macOS 26.6 arm64、Apple M1 Pro、8 logical CPU、32 GiB 内存；Python 3.12.14、SQLite 3.53.1、Flask 3.1.3、Jinja2 3.1.6、Werkzeug 3.1.9、Waitress 3.0.2；单个服务进程、8 线程。本机浏览器 Chrome 157.0.8103.51，外部 Playwright 1.58.2。没有新增应用运行依赖。

本次实际执行命令：

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_auth_browser --availability --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir docs/evidence/story-1.3-browser
.venv/bin/python -m scripts.verify_availability_performance --output-dir docs/evidence/story-1.3-performance
```

脚本默认可复跑入口见 README，可将输出指向 `work/` 保留原始证据。性能进程通过测试入口 spawn 后调用 `waitress.serve`，配置详情及完整调用入口见环境文件。临时库、随机口令和服务生命周期由脚本清理，未触碰默认演示库。

## 调试及边界说明

初次完整 Python 回归揭示 `0001-01-01T00:00` 转为 UTC 后在格式化阶段溢出成 year 0；已调整为先完成未来窗口拒绝，再转换日期，针对该输入验证 400 且无 500。浏览器首次未找到 Playwright 自带 Chromium，按已有显式 `--browser-executable` 选项使用本机 Chrome；跨日浏览器断言也修正为有效 30 分钟的 23:30→次日 00:00，以准确验证单日边界。以上问题已修复/重跑，表中为最终实际结果。

真实性能只证明此本机固定负载达到 NFR-03；未据此宣称生产容量、人类试用或后续预约写入的一致性已通过。当前故事无未完成的实施验收项；后续业务写入仍须在提交时再次验证时间、容量与占用。
