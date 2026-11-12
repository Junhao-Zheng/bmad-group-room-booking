# 课题组活动与会议室预约

软件工程管理课程项目。选题及使用对象已由用户确认。Story 1.1—1.2 已实现预置账号登录、身份显示、退出、会议室目录和共享日程；可用性查询、预约及管理能力待后续故事交付。

本仓库按实际发生的工作保存 BMAD 产物和过程证据。实验 B 按用户转述的教师要求免做，实验 A 保留。人数和截止日期不作为当前阶段的阻塞条件。

## 当前材料

- [产品简述草案](_bmad-output/planning-artifacts/product-brief.md)：使用对象、问题假设、范围和验证目标。
- [补充规则](_bmad-output/planning-artifacts/briefs/brief-group-room-booking-2026-11-12/addendum.md)：11 项假设、边界案例和实验 A 准备要求。
- [人机决策日志](decision-log.md)：目前 3 条真实人工决定，尚无人工技术否决。
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

`seed_demo_rooms` 只补充三间名称含「合成演示」的房间，按名称/地点识别已有房间，可重复运行且不覆盖容量或业务数据。它与账号初始化一样使用 `BOOKING_DB_PATH`；在旧 Story 1.1 数据库上运行也会非破坏性补齐查询表，保持 `user_version=1`。不需要演示房间时可省略该命令，首页显示空目录。默认演示库没有预约或停用，因此查询显示空日程；下方 `--schedule` 浏览器验证会在独立临时库建立有完整占用槽的合成预约与跨日停用，以复现有日程、历史、取消排除和隐私场景。应用没有预约/停用写接口，也不把测试夹具写入演示库。

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

## AI 使用声明

当前材料由 Codex 协助整理和起草，用户负责确认选题、使用对象及任务边界。精确模型版本未在当前可核验输出中提供，后续会话应保存界面中的模型信息，不能猜填。

AI 自主提出的业务规则按假设标注，不作为已完成访谈或用户已逐条批准的证据。人工决策与 AI 的编辑、检查记录分开保存。Git 提交以 Codex 标识记录本次 AI 操作，不代表组员贡献。

