# 课题组活动与会议室预约

软件工程管理课程项目。选题及使用对象已由用户确认。Story 1.1—1.3、2.1—2.4 与 3.1 已实现预置账号登录、身份显示、退出、会议室目录、共享日程、可用会议室查询、创建预约、原提交意图可靠确认、个人预约四态查询/完整详情、确认取消本人未开始预约，以及管理员新增/修改会议室和容量保护。停用管理与管理员取消属于后续故事。

本仓库按实际发生的工作保存 BMAD 产物和过程证据。实验 B 按用户转述的教师要求免做，实验 A 保留。人数和截止日期不作为当前阶段的阻塞条件。

## 当前材料

- [产品简述草案](_bmad-output/planning-artifacts/product-brief.md)：使用对象、问题假设、范围和验证目标。
- [补充规则](_bmad-output/planning-artifacts/briefs/brief-group-room-booking-2026-11-12/addendum.md)：11 项假设、边界案例和实验 A 准备要求。
- [人机决策日志](decision-log.md)：目前 4 条真实人工决定，尚无人工技术否决。
- [课程要求与状态](docs/course-scope.md)：逐项区分已做与待做。
- [下一会话交接](docs/next-session-prd.md)：在独立会话中执行 PRD 工作流的输入说明。
- [初始化证据](docs/evidence/setup-2026-11-12.md)与[用户输入摘录](docs/evidence/user-inputs.md)。

当前 PRD、架构及故事基线见 `_bmad-output/`；首个认证故事的技术验证见 [Story 1.1 验证记录](docs/evidence/story-1.1-verification.md)。实验 A 尚未执行；本次 AI 实施与测试不代表人工验收或教师 M1/M2 评审。

## 环境

- BMAD Core 与 BMad Method：6.12.1，与讲义参考版本一致。
- 项目级技能：`.agents/skills/`，配置和共享脚本：`_bmad/`。
- 本机工具环境：Python 3.12.14、uv 0.13.7，位于未入库的 `.tools/`。
- 应用采用 Python 3.12.14、SQLite 3.53.1、Flask 3.1.3、Jinja2 3.1.6、Werkzeug 3.1.9、Waitress 3.0.2；直接与传递依赖均记录于 `uv.lock`。

在本目录使用 BMAD 前，激活工具环境：

```bash
source .tools/bin/activate
uv --version
uv run --no-project --python .tools/bin/python _bmad/scripts/resolve_config.py --project-root .
```

其他机器需先安装 Python 3.11+，再在本目录重建工具环境：

```bash
python3 -m venv .tools
.tools/bin/python -m pip install uv==0.13.7
source .tools/bin/activate
```

BMAD 已随仓库保存，无需覆盖安装。若需要恢复项目级安装，使用以下固定版本命令：

```bash
npx --yes bmad-method@6.12.1 install --directory . --modules bmm --tools codex --communication-language Chinese --document-output-language Chinese --user-name 课程项目组 --no-shims --yes
```

本机已验证配置与定制解析脚本可运行。

## 运行身份与日程故事

从本项目目录运行。应用要求 Python **3.12.14**，其链接的 SQLite 须 ≥3.51.3；本机 `.tools/bin/python` 已核验为 SQLite 3.53.1。其他机器的 `.tools/bin/python` 可能只是用于安装 uv 的 Python 3.11，因此按以下命令让 uv 获取指定应用解释器，再按现有锁文件创建 `.venv`。数据库必须在本机磁盘，不能放在网络共享盘。

```bash
source .tools/bin/activate
uv python install 3.12.14
uv sync --frozen --python 3.12.14
uv run --frozen python -m scripts.init_demo
uv run --frozen python -m scripts.seed_demo_rooms
uv run --frozen waitress-serve --listen=127.0.0.1:8000 --threads=8 --call booking_app:create_app
```

应用启动仍会检查实际链接的 SQLite 版本与 Asia/Shanghai 时区；版本低于 3.51.3 时拒绝启动，不会因为 Python 版本正确而跳过检查。

初始化时以隐藏输入分别设置三个**合成演示账号**的密码，每个至少 12 字符。账号去掉首尾空白后最多 **256 UTF-8 字节**，密码最多 **1024 UTF-8 字节**；密码不去空白，初始化和登录共用上述字节限制并拒绝无效 Unicode。没有内置共享密码；请保存自己输入的密码。数据库只保存 scrypt 哈希。若终端无法隐藏输入，CLI 会停止，须改用支持隐藏输入的终端或权限 600 的私有配置文件，不会回退到明文回显。

| 账号 | 显示名 | 角色 |
| --- | --- | --- |
| `demo_member_a` | 演示成员甲 | 成员 |
| `demo_member_b` | 演示成员乙 | 成员 |
| `demo_admin` | 演示管理员 | 管理员 |

打开 [本机登录页](http://127.0.0.1:8000/login)，登录后在首页查看房间名称、地点和容量，选择会议室及北京时间日期，点击「查看日程」。结果区保留查询条件，明确显示查询中、成功、空结果或错误；共享预约仅显示活动名、预约人显示名、房间、时间与状态，停用显示时间及原因。历史日期和跨日停用同样可查询，结束恰为午夜的记录不进入下一天。使用顶栏按钮退出；刷新不会延长 8 小时绝对有效期，退出只撤销当前会话。界面可用键盘操作，并适配手机宽度。

`seed_demo_rooms` 只补充三间名称含「合成演示」的房间，按名称/地点识别已有房间，可重复运行且不覆盖容量或业务数据。它与账号初始化一样使用 `BOOKING_DB_PATH`；在旧 Story 1.1 数据库上运行也会非破坏性补齐查询表，保持 `user_version=1`。不需要演示房间时可省略该命令，首页显示空目录。默认演示库没有预约或停用，因此查询显示空日程；下方 `--schedule` 浏览器验证会在独立临时库建立有完整占用槽的合成预约与跨日停用，以复现有日程、历史、取消排除和隐私场景。Story 2.1 提供预约创建接口；停用写接口尚未交付。验证器不把测试夹具写入演示库。

初始化和启动命令可重复执行。重复初始化仍会提示输入合规口令，但只补缺失账号，**不会重置已有密码、显示名或角色，也不会清除已有数据**。停止后重启服务保留未到期会话。不要删除数据库来升级应用；schema 版本不兼容时启动会明确停止。

默认数据文件是项目目录下 `instance/booking.sqlite3`，与启动时的临时工作目录无关。可用环境变量 `BOOKING_DB_PATH` 指定另一个本地文件；初始化与服务必须使用同一路径。新建数据库权限为 600，默认目录权限为 700，运行库、私密配置和备份均已忽略。

非交互初始化接受权限为 600 的私有 JSON 文件：顶层必须是对象，其中 `users` 为数组，每项含 `username`、`display_name`、`password`、`role`；至少两个 `member` 和一个 `admin`。文件放在 `instance/` 或以 `.credentials.json` 结尾，切勿提交真实口令。

```bash
chmod 600 instance/demo.credentials.json
uv run python -m scripts.init_demo --credentials-file instance/demo.credentials.json
```

默认只在 `127.0.0.1:8000` 运行一个 Waitress 进程、8 个线程，无 debug/reloader。`APP_ORIGIN` 默认精确为 `http://127.0.0.1:8000`；浏览器也须使用该地址，不要替换成 `localhost`。如修改端口，启动时同步设置 `APP_ORIGIN`。端口须为 1—65535；配置中的 HTTP `:80` 和 HTTPS `:443` 会按浏览器 Origin 格式省略，其他端口保留。`TRUSTED_HOSTS` 默认 `127.0.0.1,localhost`，不信任代理头。HTTP 仅供 loopback 课堂演示；其他部署需要 HTTPS、`COOKIE_SECURE=true` 和匹配的 `APP_ORIGIN`/`TRUSTED_HOSTS`，公网部署不属于当前交付。

交互登录页需要 JavaScript。登录和退出请求含响应正文读取最多等待 20 秒，超时会恢复按钮并提示结果未确认；不会自动重试，需自行重试或重新打开页面。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests -v
uv run python -m scripts.verify_auth_http
```

第二条命令要求本机 8000 端口空闲（先停止手动启动的服务），会生成私有临时合成账号、重复初始化、启动同一 Waitress 命令，验证 HTTP 登录、身份、退出、旧 cookie 重放和独立会话，并自动停止服务、删除临时数据。也可加 `--port 8001`。结果不打印口令、cookie、CSRF 或 token 摘要。验证证据与桌面/手机截图见 [Story 1.1 验证记录](docs/evidence/story-1.1-verification.md)。

浏览器检查已交付为 `scripts/verify_auth_browser.py` 和 `.cjs`，需要 Node.js 20+，外部 Playwright 固定为 **1.58.2**，不属于应用运行依赖。以下安装到忽略的 `work/`，并下载其匹配的 Chromium：

```bash
npm install --prefix work/browser-tools --no-save --package-lock=false playwright@1.58.2
work/browser-tools/node_modules/.bin/playwright install chromium
uv run --frozen python -m scripts.verify_auth_browser --output-dir work/browser-verification
node --test tests/test_auth_js.cjs
uv run --frozen python -m scripts.verify_auth_browser --schedule --output-dir work/schedule-verification
```

浏览器 runner 使用独立临时数据库、权限 600 的临时随机凭证文件和 127.0.0.1:8002，自动启动/停止 Waitress 并清理临时数据。它保留桌面/390px 手机的标签、焦点、键盘登录/退出、身份 API、退出后匿名/旧 cookie 拒绝、错误反馈及宽度检查，输出无凭证的 JSON 与截图。`--output-dir` 可指定新的证据目录；不会写入原始 Story 1.1 证据文件。`--playwright-root` 可指定其他安装位置下的 `node_modules`；`--browser-executable` 可选择已有 Chrome/Chromium 可执行文件，不依赖任何特定机器路径。末条 Node 测试用可控计时器验证响应头/正文停滞均在设定的 20 秒期限取消并恢复控件，无须实际等待 20 秒。

Story 1.2 的 49 项 Python 测试、认证 JavaScript 超时回归、桌面/手机有日程与空日程检查见 [Story 1.2 验证记录](docs/evidence/story-1.2-verification.md)。`--schedule` 仍执行完整的浏览器登录/退出检查，另验证等待反馈、字段错误、条件保留、半开午夜、JSON/DOM 白名单及 HTML 文本不执行。测试和浏览器库均独立于默认演示库。

Story 1.3 首页现可按北京时间起止时段和人数查询可用会议室；`GET /api/availability?start=2026-11-13T10:00&end=2026-11-13T11:00&attendees=10` 接受当前时刻之后、30 天内的同日半小时时段（最长 4 小时）。示例日期须按实际运行日期调整。无匹配返回 200 空列表，非法条件返回 400 字段提示；查询不保留时段。查询与现有日程、登录退出互相独立。

完整复跑（浏览器依赖安装同上）：

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_auth_browser --availability --output-dir work/availability-browser
.venv/bin/python -m scripts.verify_availability_performance --output-dir work/availability-performance
```

`--availability` 同时运行登录、退出及日程回归，检查 1280×800 和 390×844 布局，并检查成功/空结果后的按钮焦点及后续 Tab 顺序。性能脚本建立独立临时数据库和 10 个随机口令账号，以固定种子 20261112、固定北京时间 2026-11-12 08:00 准备 10 房间及 1000 条预约，启动单进程 8 线程 Waitress，10 个认证客户端执行 20 次预热及 200 次完整 HTTP 测量。结束后自动停止服务并删除临时账号、数据库，不需要运行默认演示服务。每轮首先以新 run_id 写入 INCOMPLETE，使旧 PASS 失效；完成测量、数据检查和服务清理后才发布最终结果。环境保存真实 UTC 开始时间、run_id、应用源文件及测量脚本 SHA-256。输出保留所有 220 个样本（包括慢请求/失败）、类型严格的完整预期与实际 DTO、夹具、环境、最近秩 P95；无法解析的响应只保存 HTTP 状态、错误类型、字节长度及 SHA-256，不保存原正文。任意错误、错误结果或 P95 超过 1000 ms 均以非零退出码报告。固定 Clock 只在测试配置下注入，没有 HTTP 时间后门。

初版 59 项 Python 测试、13 项 JavaScript 测试及性能原始记录保留在 [Story 1.3 初版验证记录](docs/evidence/story-1.3-verification.md)。评审修复后的定向测试、真实浏览器及性能复跑见 [Story 1.3 评审修复验证](docs/evidence/story-1.3-reviewed-verification.md)。已登记性能负载全部为 30 分钟查询，其中 80% 执行 SQL 可用性筛选、20% 为人数 1001 的合法空结果快路径；报告分别列出两类样本数及 P95。该负载不代表 4 小时查询或长停用的最坏性能，也不代表实际课题组试用或生产规模。

## 创建预约与重复确认（Story 2.1—2.2）

在首页先查询时段和人数，点击结果房间的「选择并填写活动」，填写活动名称、用途并确认。提交过程中锁定创建输入与查询选择控件；成功显示预约编号及北京时间时段。服务在 `BEGIN IMMEDIATE` 后重新检查真实会话、当前容量、时间窗口及预约/停用占用，预约、完整半小时槽及一条 `booking.created` 审计原子提交。用途与人数不进入共享日程或普通成员冲突详情。文本按 Unicode 字符计数，以纯文本显示。

接口为 `POST /api/bookings`，接受 JSON 整数 `room_id`、`attendees`，以及 `title`、`purpose`、`start`、`end`、`intent_key`。人数不接受布尔、浮点或数字字符串；时间复用查询规则。首次成功为 201，响应仅一层 `data={booking:BookingFull,replayed:false}`。所有 POST 仍须同源 Origin 及 CSRF。重复初始化可在原 `user_version=1` 数据库补齐 `audit_events`，保留全部旧数据；旧库首次运行新版前请执行上面的初始化命令，启动检查不会静默升级缺失表。

成功 key 与规范化六字段 JSON 持久保存在数据库，按成员隔离。同成员相同 key、相同规范化内容返回 **200**，`data={booking:BookingFull,replayed:true}`；原预约已开始、已结束、已取消或房间容量降低也能确认原 ID 与查询时当前状态、房间及显示名。相同 key 变更实质字段返回 409 `IDEMPOTENCY_MISMATCH`；明确失败不会占用 key，重放不会新增预约、占用槽或审计。

本页表单使用 32 字节安全随机提交键，相同规范化六字段保留原键。网络断开、20 秒超时（含正文）或响应格式异常会显示「未能确认」，保留内容；点击「重试确认原预约」即可用原键确认。成功后仍可点击「再次确认原预约」，不会自动清空表单。活动名称/用途的实质编辑、选择不同房间或不同查询条件会生成新意图；仅 Python `str.strip()` 等价的首尾空白不算修改，包括 U+0085 和 U+001C—1F，但不去除 U+FEFF。点击「开始新预约」明确结束当前表单，再查询选房。提交期间锁定相关输入、查询、房间选择及新预约按钮；不会自动重提。本人取消现已由 Story 2.4 交付；管理员干预和停用管理接口仍属于后续故事。

复跑本故事（均使用隔离临时文件库，自动停止服务和清理测试凭证）：

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_create_booking_http --output-dir work/create-booking-http
.venv/bin/python -m scripts.verify_auth_browser --booking --output-dir work/create-booking-browser
.venv/bin/python -m scripts.verify_replay_intent_http --output-dir work/replay-intent-http
.venv/bin/python -m scripts.verify_auth_browser --replay --output-dir work/replay-intent-browser
```

浏览器验证沿用上述 Playwright 1.58.2 安装；未下载匹配 Chromium 时可通过 `--browser-executable /absolute/path/to/chrome` 指定已有浏览器。`--booking` 同时验证登录退出、日程与可用性回归，使用 1280×800 和 390×844 视口。HTTP 验证器使用 20 个不同成员、独立 cookie 会话及不同 key，经 8 线程 Waitress 同时争用同室同槽，保存全部响应、最终预约/槽/审计及审计故障回滚证据；不把锁超时视为占用冲突。完整结果见 [Story 2.1 验证记录](docs/evidence/story-2.1-verification.md)。

Story 2.2 的 HTTP 验证器让 20 个独立客户端复制同一登录凭证，但各自拥有 CookieJar，通过屏障同时提交同一意图，断言 1×201 + 19×200、原 ID 一致及数据库一条预约/一次创建审计。随后实际停止并重启 Waitress，以故障 writer 证实重放不调用审计、失败整体回滚且原失败 key 可重用。`--replay` 浏览器验证涵盖原有登录退出、查询与创建回归，并截断已成功提交的首个响应，保存原键重试与实质编辑新意图的原始网络证据和 key SHA-256，不保存会话凭证。当前 `--booking` 同样验证最新创建/确认行为。原始结果与验收映射见 [Story 2.2 验证记录](docs/evidence/story-2.2-verification.md)。

## 我的预约与完整详情（Story 2.3）

登录后通过顶栏「我的预约」进入 `/my`。页面自动读取本人的记录，可选择全部、待开始、进行中、已结束、已取消并点击「查看预约」。列表按开始时间、编号均倒序；点击「查看详情」读取最新完整业务信息、房间、北京时间和取消事实。未取消、未填写取消原因均有明确含义；姓名、活动名称、用途和原因按纯文本显示。页面提供加载、空记录、错误及重新登录反馈，20 秒请求超时后恢复控件，只在用户主动操作时重试。键盘可依次访问顶栏预约、我的预约、退出；打开详情后焦点移至详情标题。待开始记录可按下方 Story 2.4 的确认流程取消。

`GET /api/bookings/mine` 接受可选 `status=pending|in_progress|ended|cancelled`，返回精确 `ListResult<BookingFull>`。缺省为全部；空字符串和其他非法状态返回 400，合法空结果返回 200。个人列表始终限定当前会话用户，忽略客户端的 `user_id`、`owner_id` 等身份选择；管理员的个人列表也只返回本人。`GET /api/bookings/ID` 返回本人或当前数据库角色为管理员可读的 `BookingFull`，他人及合法不存在记录统一 404。路径 ID 按严格正 64 位十进制文本验证，超长数字返回 400。未认证 API 返回 401 JSON，`/my` 跳转登录页；读取服务在短事务内重新核验真实会话，以同一次 Clock 取时确定状态，不写业务/槽/审计。

复跑命令（浏览器安装方法与上文相同）：

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_history_browser --output-dir work/history-browser
.venv/bin/python -m scripts.verify_auth_browser --replay --port 8005 --output-dir work/history-regression-browser
.venv/bin/python -m scripts.verify_create_booking_http --output-dir work/history-create-regression
.venv/bin/python -m scripts.verify_replay_intent_http --output-dir work/history-replay-regression
```

历史浏览器验证使用独立临时文件库、固定测试 Clock、四个随机密码合成账号和只用于测试的历史夹具，默认端口 8004；没有 HTTP 造数或改时钟入口。覆盖 1280×800 和 390×844 的四态筛选、空列表、80/500 字符纯文本、完整详情、拒绝与失效、错误恢复及键盘登录退出。它将每次运行保存在独立 `runs/<run_id>`，总结果中的 `artifact_directory` 指向该次截图、原始 JSON 响应和读取前后数据库快照；只在校验、停服及临时文件清理完成后写 PASS。可加 `--browser-executable /absolute/path/to/chrome` 使用已安装浏览器。测试凭证只存临时目录，不进入仓库。

原始结果及逐项验收映射见 [Story 2.3 验证记录](docs/evidence/story-2.3-verification.md)。本次全量 100 项 Python、44 项 JavaScript 测试，以及历史页面/既有创建重试真实浏览器、20 客户端创建与重放、审计故障和重启回归均通过。

## 确认取消本人预约（Story 2.4）

在「我的预约」打开待开始记录，勾选「我确认取消上方这条预约」后点击「确认取消本预约」。成功显示取消时刻和操作者、保留历史并立即释放时段，个人列表自动刷新；回到预约页重新查询日程与可用性即看到释放结果。已开始或结束会解释不能取消；已取消记录可再次确认原状态，不覆盖取消信息。

`POST /api/bookings/ID/cancel` 只接受空 JSON 对象 `{}`，仍须有效会话、精确 Origin 和 CSRF。服务在 `BEGIN IMMEDIATE` 后取一次 Clock、重新认证，先限定本人且 kind=booking，再处理重复取消。首次仅允许 `t < start`，等号及以后返回 409 `TRANSITION_CLOSED`；管理员走此入口也仅可取消自己且遵守相同期限。他人、不存在和停用 ID 统一 404。成功返回精确 `BookingFull`；预约取消字段、全部槽删除与一条 `booking.cancelled_by_member` 审计同事务，审计失败完整回滚。

提交中锁定相关控件。网络失败、响应未知或 20 秒超时（含正文）保留原记录，须主动点击「重试确认原预约取消」，不会自动发请求。服务器拒绝保留详情并恢复控件；会话失效清空受保护数据并提示重新登录。成功提示不会抢走已移到其他表单的焦点。取消后列表刷新失败会明确区分「取消已成功」与「列表刷新失败」。

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_member_cancel_http --output-dir work/member-cancel-http
.venv/bin/python -m scripts.verify_member_cancel_browser --output-dir work/member-cancel-browser
.venv/bin/python -m scripts.verify_history_browser --output-dir work/cancel-history-regression
.venv/bin/python -m scripts.verify_auth_browser --replay --port 8005 --output-dir work/cancel-replay-regression
```

新浏览器 runner 默认端口 8006，复用已验证的独立进程组清理机制，使用私有临时凭证和隔离临时库，先写 INCOMPLETE，再记录独立运行目录、环境与源码 SHA-256。只有实际 DOM、存储断言和进程清理全部成功才写 PASS。HTTP runner 使用随机空闲端口、20 个独立登录会话，保存全部并发响应、审计失败前后快照、进程重启与槽复用证据。浏览器依赖安装和 `--browser-executable` 参数同上。

本次 **119 项 Python、71 项 JavaScript** 全部通过，无 skip；新取消、原个人历史与原预约创建/重放浏览器回归均通过 1280×800 和 390×844。完整 AC 映射、原始输出和截图见 [Story 2.4 验证记录](docs/evidence/story-2.4-verification.md)。成员与管理员取消竞争保留到 Story 2.5 联合验收，本次没有实现或声称验证管理员取消/停用撤销。Sprint 1 的成员闭环是 2026-11-12 实际压缩迭代成果，不代表四周研发、真实团队会议或人类/教师验收。

## 会议室管理与容量保护（Story 3.1）

管理员登录后通过顶栏「管理」进入 `/admin`，首次打开即可填写新增资料或选择会议室编辑。名称、地点去首尾空白后分别为 1—80、1—120 个 Unicode 字符，容量为 1—1000 整数；勾选核对确认后提交。编辑保留原编号，名称与地点组合唯一，同值保存不增加审计。取消编辑可回到新增表单；普通成员没有管理入口，直接打开管理页或请求管理 API 均返回 403，匿名页面跳登录、API 返回 401。

`POST /api/admin/rooms` 返回 201 Room；`POST /api/admin/rooms/ID` 接受完整 `name,location,capacity` JSON 对象，返回 200 Room。容量不接受布尔、浮点和数字字符串；路径编号必须是规范正 64 位整数。全部写入要求 Origin、CSRF 和真实有效管理员会话，服务在取得 SQLite 写锁后再次确认身份/角色。重复组合返回 409 `ROOM_DUPLICATE`。降低容量会在同一事务检查所有尚未结束且未取消预约，包括进行中预约；不足返回 409 `CAPACITY_CONFLICT`，管理员看到冲突编号、北京时间和人数，名称/地点也不保存。容量等于人数允许，已结束、已取消和停用记录不阻止降低。

一次真实新增/修改与一条 `room.created`/`room.updated` 审计共同提交；快照仅含 `id,name,location,capacity`，修改包含 before/after，reason 为 null。审计失败全部回滚。预约创建和降容量共用写锁，旧成功预约意图仍可在取消或结束后降容时重放。没有房间硬删除或永久下线开关。

提交期间锁定管理控件；字段错误、冲突和服务失败保留输入。网络断开、响应未知或 20 秒超时（含正文）不会自动重提，请先「刷新目录」核对实际保存结果；新建请求已提交时可从目录选择原房间继续编辑。会话失效保留表单并提示重新登录，不自动提交；成功后的目录刷新失败会明确保留已保存结果。等待期间移到退出等其他表单的焦点不会被完成提示抢走。

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_room_management_http --output-dir work/room-management-http
.venv/bin/python -m scripts.verify_room_management_browser --output-dir work/room-management-browser
.venv/bin/python -m scripts.verify_auth_browser --replay --port 8005 --output-dir work/room-booking-regression
.venv/bin/python -m scripts.verify_member_cancel_browser --output-dir work/room-cancel-regression
```

浏览器工具安装方法和 `--browser-executable` 参数同上；管理 runner 默认端口 8007。新验证器使用独立临时文件库、私有随机凭证、固定测试 Clock，复用已验证的进程清理，先写 INCOMPLETE，完成原始 HTTP/DOM/存储断言和清理后才写 PASS，记录运行前后源码指纹。此次 **133 项 Python、103 项 JavaScript 全部通过，无 skip**；20 轮真实预约/降容量竞争、故障回滚、停服重启和旧意图重放通过。1280×800、390×844 管理路径和原预约/取消浏览器回归通过。逐项 AC、原始输出、网络响应和截图见 [Story 3.1 验证记录](docs/evidence/story-3.1-verification.md)。

## AI 使用声明

当前材料由 Codex 协助整理和起草，用户负责确认选题、使用对象及任务边界。精确模型版本未在当前可核验输出中提供，后续会话应保存界面中的模型信息，不能猜填。

AI 自主提出的业务规则按假设标注，不作为已完成访谈或用户已逐条批准的证据。人工决策与 AI 的编辑、检查记录分开保存。Git 提交以 Codex 标识记录本次 AI 操作，不代表组员贡献。



第一个史诗的复盘修补及复跑证据见 [epic-1-followup](docs/evidence/epic-1-followup/verification.md)。认证浏览器报告先写 `INCOMPLETE`，通过后包含真实环境版本、运行前后未变化的应用/验证源码哈希，以及本次截图哈希。HTTP 验证器显式使用 loopback HTTP 配置，父环境的 HTTPS cookie/host 配置不会影响隔离测试。

Story2.4评审后主流程全量复验121项Python/86项JS，16项发现全部闭环，0defer；[最终证据](docs/evidence/story-2.4-review-fixes/parent-final-qa.json)。

Story3.1评审后全量139项Python、141项JS通过；[最终验收证据](docs/evidence/story-3.1-review-fixes/parent-final-qa.json)。
