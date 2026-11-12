# Story 1.1 独立差异评审与逐项裁决

评审基线：837f30b48199ede90c4bfbb970080361db051070。首轮diff 117291 bytes。三个无对话历史的同配置AI评审上下文在全部启动后收集结果；不等于三位组员。Blind finding floor=min(floor(sqrt(117.291)+1),10)=10。以下保留全部18项，重复只在修复分组时合并，不从发现计数中消失。

| ID/镜头 | 发现 | 裁决及证据 | 路由 |
|---|---|---|---|
| B1 blind | 到期/放弃会话不清理，表长期增长 | low：到期读取正确拒绝，短期课程演示增长无实质功能影响；增加维护分支超过直接修正，不据此加后台任务 | reject-low |
| B2 blind | 孤立Unicode代理字符导致用户名SQL绑定/密码编码500 | medium：auth.py接受非空字符串后直接交给SQLite/scrypt；应当在编码边界拒绝非法Unicode | patch，和E1同因 |
| B3 blind | noscript声称表单仍可用，但成功后停在JSON | low：API按契约返回JSON，页面选择JS交互；真实缺陷是noscript误导，改为明确启用JS，不新增另一套HTML写协议 | patch文案 |
| B4 blind | APP_ORIGIN接受非法端口及显式默认端口 | medium：urlsplit未读取port，字符串原样比较与浏览器标准Origin不一致 | patch，和E4同因 |
| B5 blind | 手工伪造version=1且列名相同但无约束的DB可启动 | low：初始化始终生成约束，触发条件是外部修改/伪造schema；当前课堂常规路径不会遇到，复杂指纹校验不采纳 | reject-low |
| B6 blind | 17000字口令可初始化但超过16KiB请求上限 | medium：初始化与HTTP输入能力不一致，已定位MAX_CONTENT_LENGTH和seed校验；需同一兼容边界 | patch，和E2同因 |
| B7 blind | 私有JSON顶层array/null引发CLI TypeError回溯 | medium：直接json对象索引users；应先检查dict再交给现有受控错误 | patch，和E3同因 |
| B8 blind | getpass无TTY时可能回显而继续 | medium：getpass默认警告而不停止；已有私有文件方式，可将GetPassWarning转为受控失败 | patch |
| B9 blind | commit失败测试实际在COMMIT前抛异常 | medium：db事务yield之后测试抛错，证明普通回滚而非COMMIT异常；准确改名并另加SQL COMMIT处故障注入 | patch测试/证据 |
| B10 blind | 浏览器仅保存PASS/截图，没有可复跑入口 | medium：实际脚本在被忽略work/browser-check.cjs，未交付；保留为便携脚本并给出依赖/运行步骤 | patch，和V1同因 |
| E1 edge | JSON孤立代理字符500 | medium：同B2，不单独算新根因 | patch |
| E2 edge | 配置凭证超过HTTP请求长度 | medium：同B6，不单独算新根因 | patch |
| E3 edge | 顶层array/scalar/null文件回溯 | medium：同B7，不单独算新根因 | patch |
| E4 edge | 默认端口Origin与浏览器不一致 | medium：同B4，不单独算新根因 | patch |
| E5 edge | fetch永久挂起导致按钮一直禁用 | medium：auth.js无超时，网络不确定路径应恢复可操作并提示确认结果；20秒超时高于15秒存储等待 | patch |
| E6 edge | terminate后10秒仍未退出则可能留下验证服务 | maybe-false：当前仅启动默认Waitress且无忽略SIGTERM逻辑，实际退出通过；没有可达挂起证据，潜在影响仅外部故障下测试清理，属未证实low | reject，若今后复现再修 |
| V1 verification | 正常验证不执行浏览器JS，删除CSRF头仍会绿 | medium：服务器测试确实自行构造正确头，无法捕捉页面回归；“不存在忽略目录脚本”表述不准确，但未交付/不可复跑这一结论成立 | patch，和B10同因 |
| V2 verification | 权限644私有文件拒绝未被CLI负向测试覆盖 | medium：seed_users单测绕过main；HTTP脚本只有600合法输入，增加真实子进程拒绝与不改库/不泄漏断言 | patch |
| P1 主代理 | README工具Python3.11与应用精确3.12.14启动指令不衔接 | medium：新机器照抄.tools/python可能版本不符，缺少取得应用Python步骤；增加uv管理3.12.14、frozen同步和fresh环境复验 | patch |

保留的修复均为已演示输入/配置/验证路径的局部修正，不新增产品功能或公共业务API；首轮需要变更，因此首轮评审不算通过。修复及最终复跑结果另记，不能提前标done。AI评审取舍不计入人类否决日志。

## 修复闭环与主代理验收

全部保留patch已完成：有效Unicode和兼容字节上限、Origin规范化、CLI受控拒绝、noscript文案、20秒取消、精确COMMIT调用故障、可复跑浏览器runner及fresh环境说明。原始初版测试/截图未覆盖；修订证据单独保存。被拒绝的低风险改进没有加入产品，不存在悬而未决的high/medium。

主代理读取修订差异并复跑：33项Python全量测试（0 skip）、2项JS超时测试、13请求真实Waitress HTTP均通过；隔离目录重新uv sync --frozen --python 3.12.14并运行同一HTTP脚本通过。浏览器修订runner实际通过桌面和手机操作；主代理另用Playwright1.62.1查看初版登录布局，无溢出/脚本异常。没有把这些自动化证据算作人工验收。

证据：story-1.1-final-tests.txt、story-1.1-final-js.txt、story-1.1-final-http.json、story-1.1-fresh-install.txt、story-1.1-fresh-http.json（均在上级evidence目录）；修订浏览器见story-1.1-post-review-browser/browser-results.json。
