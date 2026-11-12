---
reviewer: brief_grounding
lens: technology-reality
date: 2026-11-12
verdict: concerns
critical: 0
high: 0
medium: 1
low: 0
---

# 架构技术现实核验

## 结论

技术选型、版本和框架起点均有真实依据，未发现虚构 starter 或明显版本冲突。Python 与 SQLite 基线已在本机独立复测。存在一项中等输入边界缺口，建议交付实现前修正文档。这个结论仅覆盖设计可实现性，不证明应用已运行、NFR 已达标或教师门禁已通过。

完整读取范围：本 run 的 `ARCHITECTURE-SPINE.md` 与 `../../architecture.md`，包括其组件、数据协议、认证、HTTP、备份及测试章节。未修改架构、代码或 Git。

## 发现 R-REALITY-01

**中等：所有传入资源 ID 需要在绑定 SQLite 之前限制整数范围。**

- 位置：`architecture.md` §5.2 第 106 行、§7 的正整数 ID 协议；spine 的 Consistency Conventions / IDs。
- 当前要求只规定 ID 是正整数，Python 的整数可大于 SQLite 参数绑定可接受的有符号 64 位范围。`9223372036854775808` 满足现有格式规则，传入房间查询或预约详情查询后，标准库 `sqlite3` 会抛出 `OverflowError`。按当前异常映射，它可能成为 500，而不是输入错误或不存在资源的稳定结果。
- 本机复测：`SELECT ?` 绑定 `9223372036854775807` 成功；绑定 `9223372036854775808` 得到 `OverflowError: Python int too large to convert to SQLite INTEGER`。该检查只使用内存数据库，不触碰项目业务数据。
- 建议：统一规定所有路径、查询和 JSON 中的数据库 ID 满足 `1 <= id <= 2**63 - 1`，越界在 SQL 绑定前映射为明确的输入错误；也可规定超范围路径 ID 为 404，但所有入口必须一致。保留鉴权优先，避免为无权访问者泄漏对象信息。
- 实施验证：对房间 ID、预约 ID、停用 ID 的 `2**63-1`、`2**63`、超长十进制、bool/float 分别断言；格式通过但不存在的最大 ID 应得到 404，超范围输入不应产生 500。

## 独立版本与兼容性核验

| 项目 | 核验结果 | 证据 |
|---|---|---|
| CPython 3.12.14 | `.tools/bin/python` 实测 3.12.14；官方发布页存在。页面明确已有更新版，架构没有声称它是最新版本 | [Python 发布页](https://www.python.org/downloads/release/python-31214/) |
| SQLite 3.53.1 | 同一解释器的 `sqlite3.sqlite_version` 实测为 3.53.1；官方发布页存在 | [SQLite 发布页](https://sqlite.org/releaselog/3_53_1.html) |
| Flask 3.1.3 | 官方发布记录与 PyPI 元数据一致；Requires-Python 为 `>=3.9`；要求 Werkzeug>=3.1.0、Jinja2>=3.1.2，与所选版本兼容 | [官方变更](https://flask.palletsprojects.com/en/stable/changes/)、[版本元数据](https://pypi.org/pypi/Flask/3.1.3/json) |
| Jinja2 3.1.6 | 官方发布记录存在；Requires-Python 为 `>=3.7`；对应 wheel 未撤回 | [官方变更](https://jinja.palletsprojects.com/en/stable/changes/)、[版本元数据](https://pypi.org/pypi/Jinja2/3.1.6/json) |
| Werkzeug 3.1.9 | 官方发布记录存在；Requires-Python 为 `>=3.9`；对应 wheel 未撤回 | [官方变更](https://werkzeug.palletsprojects.com/en/stable/changes/)、[版本元数据](https://pypi.org/pypi/Werkzeug/3.1.9/json) |
| Waitress 3.0.2 | 官方文档与版本元数据一致，支持 Python>=3.9；无必须安装的第三方运行依赖 | [官方文档](https://docs.pylonsproject.org/projects/waitress/en/stable/index.html)、[版本元数据](https://pypi.org/pypi/waitress/3.0.2/json) |

元数据读取于 2026-11-12。Flask/Jinja2/Werkzeug/Waitress 尚未安装在 `.tools` 中，当前是已核验的拟用依赖，不是已完成应用安装。架构已把完整锁与运行测试留给实施阶段，这一区分准确。

## 决策可实现性核验

| 决策 | 核验与结论 |
|---|---|
| AD-1 单体与起点 | Flask 官方 tutorial 确实使用应用工厂、包目录和 instance 配置。架构声明只参考结构，并未虚构第三方模板或生成器。页面与 API 复用 services 是本项目设计，尚未测量其实际收益。[官方工厂示例](https://flask.palletsprojects.com/en/stable/tutorial/factory/) |
| AD-2 时间 | 本机 `ZoneInfo('Asia/Shanghai')` 可构造；Python 3.12 支持该模块。UTC 整数与半开区间是设计选择，无需声称框架自动保证。输入 ID 的整数边界见 R-REALITY-01。[官方 zoneinfo 文档](https://docs.python.org/3.12/library/zoneinfo.html) |
| AD-3 写入一致性 | SQLite 明确支持 `BEGIN IMMEDIATE` 先开启写事务；WAL 允许读写并发但不提供并行写者。使用 `isolation_level=None` 和 `LEGACY_TRANSACTION_CONTROL` 后显式 BEGIN/ROLLBACK 的方式在 Python 3.12 上实际验证成功；业务冲突分布仍需实施后测量。[SQLite 事务](https://sqlite.org/lang_transaction.html)、[Python 事务控制](https://docs.python.org/3.12/library/sqlite3.html#transaction-control) |
| AD-4 意图去重 | SQLite 支持带 WHERE 的 UNIQUE 部分索引，`WHERE kind='booking'` 可表达。持久重放顺序、用户作用域和响应契约属于应用职责，不能仅凭索引宣布通过幂等验收。[部分索引文档](https://sqlite.org/partialindex.html) |
| AD-5 会话防护 | Werkzeug 官方支持 `scrypt:32768:8:1`。服务端随机 token、CSRF、Origin、撤销与期限逻辑在该技术栈可实现，但必须由应用实现并测试，没有被当作 Flask 默认提供的功能。[安全函数](https://werkzeug.palletsprojects.com/en/stable/utils/#werkzeug.security.generate_password_hash) |
| AD-6 授权与 DTO | 服务端 actor、显式字段白名单、模板转义均与 Flask/Jinja 用法相容；这是设计契约，须以权限和泄漏测试证明，不是已验证安全结论。 |
| AD-7 状态及审计 | 同库显式事务可将业务、槽与审计原子提交。架构正确把真实变更与重放区分；取消竞争及故障注入还未实施，当前不声称有实测结果。 |
| AD-8 部署与备份 | Waitress 的 `--listen`、`--threads`、`--call MODULE:OBJECT` 选项真实存在。SQLite 官方明确 WAL 不支持跨主机网络文件系统，并说明 WAL-reset 修复从 3.51.3 起可用，所选 3.53.1 满足该条件。[Waitress CLI](https://docs.pylonsproject.org/projects/waitress/en/stable/runner.html)、[WAL 文档](https://sqlite.org/wal.html#walresetbug) |

## 实施交接说明

本次没有安装应用依赖、启动 WSGI、执行项目 NFR 或备份恢复演练，避免把技术可行性核验记成产品验收。`.python-version` 本身不能保证解释器链接的 SQLite 版本；实施时必须保留架构已有的启动版本检查并记录实际分发来源。`zoneinfo` 依赖系统 IANA 数据或 `tzdata` 包，评审机器环境检查应确认可加载 Asia/Shanghai；当前 macOS 环境已通过。[Python 数据来源说明](https://docs.python.org/3.12/library/zoneinfo.html#data-sources)

R-REALITY-01 修正后，本镜头没有其他阻止进入故事拆分的技术现实问题。版本可用性不替代依赖锁，也不替代后续功能、安全、并发和性能证据。
