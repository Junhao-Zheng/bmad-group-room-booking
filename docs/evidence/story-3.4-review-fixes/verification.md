# Story 3.4 审查修复（子任务定向验证）

已完成主流程指派的八组最小修复。代码在本报告生成前冻结，主流程负责最终全量验收。本次对话中断后沿用已写入修补；中断不是网络故障，原始 `story-3.4/` 报告未改写。主流程的 `python-all.txt`、`js-all.txt` 不属于本子任务输出，保留原状。

| 修复/分类 | 实际改动 | 针对性证据 |
| --- | --- | --- |
| 备份碰撞 B1/E1 | 目标创建/SQLite打开前以 `os.path.lexists` 检查目标及 `-wal/-shm/-journal` 全命名空间；存在文件或悬空链接即拒绝。逐suffix测试有效/无效源、原辅助文件、悬空符号链接、源库本身占目标sidecar，断言原内容保留且SQLite未打开。 | [targeted-python.log](targeted-python.log)中的6项backup测试 |
| 备份说明 B4，B2/B3边界 | README明确结构检查不等于应用兼容；schema_version=0不能用作应用恢复，恢复须schema=1及db.check_database；未成功完成CLI的中断副本不算完成备份，外部独占锁可持续等待释放/中断。未新增原子发布、deadline、CLI参数。 | [README](../../../README.md) |
| 审计静态一致性 B5/E2 | DTO验证action/type匹配、只有created允许before=null、两侧snapshot.id匹配target_id、正数ID及capacity/attendees范围。矛盾安全500，不重写历史、不按当前预约窗口拒绝历史；测试含1970年历史记录仍可读。 | [targeted-python.log](targeted-python.log)中的7项audit测试 |
| 展示字段类型 B6 | JS对每个已知快照字段验证字符串/整数及允许的null；嵌套对象、字符串容量、布尔容量/操作者、错误nullable类型整体拒绝展示。 | [targeted-js.log](targeted-js.log) |
| 筛选失效 B8 | 对象/日期input与change清空旧行并隐藏结果，提示重新查询，保留筛选值，不自动请求；generation/abort阻止旧响应恢复结果，计时器绑定本次controller。 | handler input/change/late-response测试；[browser/result.json](browser/result.json) |
| 浏览器可移植 B9 | 显式executable优先；未指定时按既有runner方式查询Playwright chromium.executablePath。CLI保持原参数，无macOS固定默认路径。 | 3项runner测试，缺省分支通过mock验证，无需安装浏览器 |
| 完整显示绑定 B10/V2 | handler使用不同的更新/取消/撤销before和after夹具；浏览器逐行6列比较完整actor/action/target/time/reason、展开后的前后值，并核独立预期更新地点、取消原因、撤销原因。 | 每视口10行完整actual/expected记录；before→after变异被断言拒绝 |
| 原因语义 V1 | Python逐action同时比较存储reason与独立预期；JS在正确原因列比较非null短/长纯文本。 | Python所有reason→null失败；JS原因列→无失败 |

## 实际执行

仅运行覆盖本次修改的测试，**16项Python、31项JS通过，正常定向测试无skip**：

```bash
.venv/bin/python -m unittest tests.test_backup tests.test_audit tests.test_audit_browser_runner -v
node --test tests/test_audit_js.cjs
.venv/bin/python -m scripts.verify_audit_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir docs/evidence/story-3.4-review-fixes/browser
.venv/bin/python docs/evidence/story-3.4-review-fixes/verify_mutations.py
```

[浏览器报告](browser/result.json)使用真实Waitress/Chrome，1280×800和390×844均PASS；测试独立临时库、临时凭证，完成进程清理，前后源码指纹一致。保留原过滤、加载、错误恢复、失效、成员拒绝、登录退出、无页面横溢出检查；新增逐单元格完整事实与编辑筛选即清结果检查。

每个视口的实际显示值与预期值保存在 `browser/runs/RUN/display-bindings-WIDTH.json`，可与同目录network响应核对。运行标识见[汇总](targeted-summary.json)。

## 变异验证

[verify_mutations.py](verify_mutations.py)只修改内存或临时副本，不改工作区产品文件：

- [Python reason→null](null-reason-mutation.log)：只跑七种真实动作测试，得到1个预期AssertionError（None != 'finished'），证明旧的漏检已补齐。
- [JS before列读after](before-cell-reads-after-mutation.log)：只执行新增完整单元格绑定测试，失败1项，显示旧/新房间名称和容量差异。
- [JS reason列置空](reason-cell-null-mutation.log)：同一完整绑定测试失败1项，原因列“无”与真实管理员原因不符。

两个JS变异日志中其余30项标为skip是`--test-name-pattern`刻意只选择这一测试，不是正常定向套件skip；正常31项JS全通过且无skip。JS套件内还通过在内存执行变异并assert.throws，持续保证显示oracle能捕获这两类变异。

三项变异结果见 [null-reason-mutation.json](null-reason-mutation.json)、[js-mutations.json](js-mutations.json)。本次未运行全量测试/并发/重启/性能回归，按指派交由主流程完成；不冒充最终独立评审。
