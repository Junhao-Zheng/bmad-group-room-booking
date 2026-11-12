# Epic 3 aggregate derivation（只读产品核对，无验收裁决）

## 范围与复跑

比较 `6644902c9e3880482d1edef75c42a1ee303ba6dd..82b4b567f27c788e062a7bc8310d0c660c69d666`，左端为 3.1 记录的实施前基线，右端为 3.4 接受提交。共 26 次提交、0 merge；范围实际交错包含 Story 2.5 管理员取消、实验/录屏准备，以及 `79fdc6a` 中历史 `tests/test_history_browser_runner.py` 的超时夹具修正，不能把整个范围变化独占归因于 Epic 3。主要产品落点为 `7d31d1a`（3.1）、`85aac3f`（3.2）、`3a33cfd`（2.5集成）、`79fdc6a`（2.5/3.3最终集成）、`82b4b56`（3.4）。所有下述实现/测试行号均按右端提交。

复跑：`python3 docs/evidence/retrospectives/derive_epic_3_aggregate.py`。脚本只读两端 git blobs，生成 `epic-3-aggregate.json`；不执行产品、不提交、不改变产品文件。JSON 保存 AST 导入及 SQL 调用位置、SCC、逐文件物理行/字节/哈希、函数跨度/语句数、提交来源和派生边界。既有 `epic-3-git.json` 的 `files` 为非 merge 累计 churn，未当成文件绝对大小；`merge_files` 单列；此范围没有 merge，应用文件没有 binary revision。

Checked scope：全部 8 个 `booking_app` Python 模块；受版本控制的 `booking_app/scripts/tests` 下 Python/JS/CJS/HTML/CSS/SQL 文件规模；人工核对四张故事卡、PRD FR-16—22/NFR、architecture §4—8、project-context、Epic 3 context；阅读主要管理服务/页面、对应测试断言和归档运行报告。文件规模不含框架安装、实验副本或证据 JSON；依赖及函数 AST 只覆盖 Python 应用层。语义重复与 JS 结构是有指向的人工检查，不是全仓 clone detector。

## 结构、规模与重复观察

1. **Python 依赖没有漂移。** 两端均为 8 模块、14 条内部导入边、0 循环，新增/删除边均为0。`web→services/auth/domain`，`services→auth/db/domain/dto`，`dto→domain` 等关系未变。`domain` 没有 Flask 导入；`services` 使用 Flask `current_app` 是基线已有事实。与 `project-context.md:14`、`architecture.md:63` 的分层方向一致；这是静态导入图结论，不覆盖动态依赖或 JS 图。
2. **SQL 未扩散到路由/纯规则。** AST 调用点 `services.py` 17→38；`db.py` 20→20、`auth.py` 7→7、`audit.py` 1→1；`web.py/domain.py/dto.py/__init__.py` 均0。计数包含 execute/executemany/executescript/commit/rollback 调用点，不是 SQL 语句或运行次数。新增业务写 `services.py:139,158,200,245,307` 均走现有 `db.write_transaction`，锁后一次 Clock，重新读取 actor，命令内写审计；读取审计 `services.py:108` 使用短读事务。认证 SQL 和注入式 audit writer 是既定边界（`project-context.md:20,24`），不能误判为越层。
3. **确有集中增长，但没有证据支持“巨型类”标签。** 应用真实最大物理文件为 `services.py` 212→453行（+241；25,758字节），9→20个函数；最长仍为原有 `create_booking` 66行，新增最大为 `create_block` 40行、`_admin_records` 35行。服务文件组织为预约创建/目录/审计查询、房间及停用命令、三种终态命令、个人/管理员查询、可用性/日程（`services.py:24,92,108,139,158,200,245,277,307,338,374,419,438`）。5个小类全部不变，最大仅6行；服务层没有类。
4. **新增管理 UI 是后续耦合关注点。** `blocks.js` 0→382行、28,074字节，是应用字节数最大的文件，物理行排第二；同一 IIFE 负责停用创建、两类完整列表、2.5管理员取消、3.3撤销以及页面忙碌/身份状态（`:10—19,65,83,124,226,289,340`）。它是范围净增长第一（累计+401/-19），不能把新增382行都归到3.3。两个独立命令的重复结构由架构明确要求（`architecture.md:83`），不宜仅为了去重合并为通用终态命令。管理读取已复用 `_admin_records`（`services.py:374`）；原因规范化复用 `normalized_text`，槽约束/事务/DTO共用。
5. **真实最大测试/runner已区分。** 所测代码目录最高为 `tests/test_auth.py` 602行（`AuthTests`含33个测试，`:41`），其次 `scripts/verify_auth_browser.cjs` 544行（浏览器场景串行验证）；二者两端均未增长。它们不是此次新增产品巨型文件。`tests/test_blocks_js.cjs` 0→446行是新增UI组合回归，不能与产品文件混算。
6. **存在低风险模式差异，未据此认定规则冲突。** Python ≥4语句的完全相同函数体扫描未发现重复；这不排除近似逻辑。`rooms.js:68` 与 `blocks.js:53` 重复20秒超时/fetch/JSON框架，前者仅检测成功 `ok/data`，后者要求精确外层；`audit.js:74` 又实现独立 GET 与 generation 防迟到。三个管理面板都使用 `admin-auth-lost` 清敏感数据（`rooms.js:80`、`blocks.js:83`、`audit.js:40`），筛选修改失效在 blocks/audit 已一致（`:216` / `:48`）。可将响应解析/身份事件列为后续统一候选，但当前差异没有单独证明真实服务返回违约或用户路径失败。
7. **参数严格程度差异有实现证据，不能扩大成需求冲突。** 2.5 路由要求精确 `{reason}`（`web.py:120`）；3.3 从 payload 取 reason 并忽略额外键（`domain.py:263`），其测试明确传入伪造取消人/时间并验证服务器身份（`test_block_revoke.py:92`）。冻结 AC 要求身份优先、原因和 ID 正确，没有要求拒绝所有未知键；3.2同样测试忽略伪造user_id/kind（`test_maintenance_block.py:76`）。因此这里只记录接口模式差异，未以“缺少未知键拒绝测试”宣称AC违约。

## 16条 AC 到实现、测试与运行记录

需求锚点：3.1卡 `:34—37`、3.2卡 `:34—37`、3.3卡 `:35—38`、3.4卡 `:34—37`；上游 `PRD.md:144—198`、`epic-3-context.md:18—33`。下表的“证据支持”表示静态实现、断言与已存在运行记录相互对应；不是本子任务重跑结果或机器验收判定。

证据简称（均为仓库相对路径）：

- **R1** `docs/evidence/story-3.1-review-fixes/parent-final-qa.json`（139唯一Python/141 JS），HTTP `.../http/http-result.json`，浏览器 `.../browser/browser-results.json`；提交 `7d31d1a`。
- **R2** `docs/evidence/story-3.2-review-fixes/parent-final-qa.json`（156唯一Python/208 JS），HTTP `.../http/http-result.json`，浏览器 `.../implementer/browser/browser-results.json`；提交 `85aac3f`。
- **R3** `docs/evidence/experiment-a-integration/parent-final-qa.json`（192唯一Python/282 JS），`.../block-revoke-http/http-result.json`、`.../block-revoke-browser/browser-result.json`；提交 `79fdc6a`。
- **R4** `docs/evidence/story-3.4-review-fixes/parent-final-qa.json`（208唯一Python/313 JS），`.../parent-http/result.json`、`.../browser/result.json`；提交 `82b4b56`。本派生另外逐个复算两个最终报告各58个源码哈希，均匹配接受提交，前后指纹相等。

| AC | 实现与测试位置 | 运行记录及核对边界 |
|---|---|---|
|3.1-1 稳定ID/唯一组合/范围/真实审计/无变化|`services.py:130,139,200`；`domain.py:211`；`tests/test_room_management.py:77,106,155,166`|R1支持201/200、快照和无变化0次writer；名称/地点/容量完整替换。|
|3.1-2 非法/重复/member/超大ID/无硬删除|`web.py:79,87`；`services.py:142,203`；`test_room_management.py:155,166,201,218`|R1支持400/409/403及数据不变；权限优先，DELETE不成功；极大ID页面精度是卡中明确保留边界，不能推称API越界失守。|
|3.1-3 降容保护所有未结束有效预约|`services.py:213`；`dto.py:119`；`test_room_management.py:175,187`|R1支持pending/in_progress冲突、等量成功、ended/cancelled忽略，冲突含管理员编号/区间/人数。|
|3.1-4 20轮预约/降容竞争及原子UI恢复|`services.py:25,201`；`test_room_management.py:134,255`；`scripts/verify_room_management_http.py`、`tests/test_rooms_js.cjs`|R1 HTTP run `d13eac0d…`：20轮/40响应，两种合法胜者各10；无未结束超员、审计链与故障回滚；R1浏览器支持保留输入。|
|3.2-1 跨日长停用/30天/槽/审计|`domain.py:230,251`；`services.py:158`；`test_maintenance_block.py:62,89,93`|R2支持30小时60槽、30天等号、1—500字原因、201及同连接单审计。|
|3.2-2 预约/停用互斥且保留原记录|`services.py:167,181`；`test_maintenance_block.py:104,112`|R2 HTTP run `52a541ee…`：20轮/40响应，booking8胜/block12胜；原预约保留、相邻跨日合法及共享槽完整。|
|3.2-3 管理过滤/精确DTO/升序/互斥四态|`services.py:374,411,415`；`dto.py:74,97`；`test_maintenance_block.py:121,138,146`|R2 HTTP精确DTO及浏览器完整字段/状态绑定证据；空/非法筛选已有明确断言。|
|3.2-4 member拒绝/审计故障/UI冲突草稿|`services.py:161,191`；`blocks.js:226`；`test_maintenance_block.py:153,163,198,217`|R2真实HTTP全回滚及浏览器原因/冲突/失败输入；没有用未授权无按钮代替直接API验证。|
|3.3-1 首次撤销完整元数据/释放全部槽|`services.py:245,264`；`dto.py:97,112`；`test_block_revoke.py:79`|R3支持200 BlockFull、原原因不变、三撤销字段/全部槽/完整before-after、一次审计。|
|3.3-2 重复保留首结果/结束等号/非法重复|`services.py:251,259,261`；`test_block_revoke.py:112,126,142`|R3测试对应过end合法重复返回首结果，非法原因400先于幂等，首次end等号409。|
|3.3-3 权限优先/失效退出降权/严格kind-ID|`services.py:249—255`；`web.py:127`；`test_block_revoke.py:150,158,177`|R3对应直接API与锁内复核；错误kind/超范围ID/失效会话不改事实。|
|3.3-4 重复竞争一次转换/故障回滚/不恢复预约|`services.py:246,264—272`；`test_block_revoke.py:204,224`|R3 HTTP run `28b9b256…`：20轮、2独立管理员、40个200、20次转换/20审计，首元数据一致；writer前后故障。客户端barrier不是每轮服务器锁等待的直接观测。|
|3.4-1 查询排序/筛选/完整审计/成员403|`services.py:108`；`dto.py:20`；`audit.js:61`；`test_audit.py:45,95,108,136,146`|R4 HTTP138权限用例；浏览器两尺寸完整display bindings、过滤失效、前后值和原因；损坏JSON安全500。|
|3.4-2 仅真实转换审计且无认证秘密|`services.py:83,150,191,224,268,298,329`；`audit.py:6`；`test_audit.py:45—91`|R4 `all_seven_actions=true`、`unchanged_retries=true`；测试逐动作原因及禁止敏感键。不是所有任意日志/所有外部输入的形式化安全证明。|
|3.4-3 真停服新PID/数据关联不变/旧意图|`scripts/verify_audit_http.py` 的停启与facts比较；历史保存见下|R4 `parent-http/runs/93a898e9d1b4ebf1c58ed75252d88c6a/restart.json:2`：PID76446停后76451，业务关联相同、旧会话有效、旧已取消记录ID1重放、审计不增；前后JSON和replay文件同目录。|
|3.4-4 schema/路径/loopback/backup/不提交秘密|`scripts/backup_db.py:13,28`；`tests/test_backup.py:19,29,42,47,69,80`；`README.md:39,44,61—117`|R4环境与backup.json支持实际配置/备份；拒绝目标sidecar、不覆盖源、600权限。文档明确结构有效≠应用兼容；停服恢复/回退仅说明，未声称灾难演练。|

## 已记录边界与缺失证据

- 上述16条都有实现、针对性测试和运行报告入口，本次未发现需要用“无测试”替代证明的业务冲突；这不等于穷尽所有路径。
- 本子任务只执行派生脚本，没有新跑HTTP、浏览器或全量测试。旧故事报告绑定当时提交；R4两份最终报告的58个文件指纹另行验证到了接受提交。3.4初版联合NFR记录仍是早先执行，最终QA明确没有冒称旧报告哈希等于最终全部源码（R4 `nfr_scope`）。
- 未系统读取全部原始会话日志，所以不推断编写动机、遗漏原因或实际人类工作量。无新的人类/教师验收、跨平台浏览器实测或灾难恢复演练证据；这些不由代码/测试成绩补造。
- 已有取舍：超大整数浏览器限制、房间完整替换的后写覆盖、跨登录不恢复草稿（3.1卡`:75,77,81`与README`:59`）；backup中断留下不完整目标及无完成时限（3.4卡`:74—75`、README`:88`）；无分页/审计默认查询性能未纳入可用性NFR（3.4卡`:79`）。本报告保留边界，不重复裁决。
- 后续可审议的维护事项只有管理UI共用请求/身份约定和 `blocks.js` 的职责拆分；本报告未自动修改，也未将维护性观察升级为AC失败。
