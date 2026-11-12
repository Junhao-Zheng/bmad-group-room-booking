# 共同运行说明（实验输入）

本目录为独立副本，已有应用、schema、测试和运行脚本与另一组完全相同。仅阅读本目录中的项目材料；不读取原始仓库、另一组、上游评审或历史会话。允许执行本机公共解释器、Node、Git基础命令及浏览器，但不借此读取外部项目材料。本限制是指令隔离，不是OS沙箱。

运行：`.venv/bin/python -m unittest discover -s tests -v`；`node --test tests/test_*js.cjs`。`pyproject.toml`与`uv.lock`锁定依赖，本目录`.venv`独立，不与原仓库共享。Playwright 1.58.2位于`work/browser-tools/node_modules`；可指定本机Chrome。不要新装或切换模型，不进行Git远端操作。

现有入口：booking_app/create_app工厂；services.py业务服务；web.py HTTP路由；domain.py输入/状态规则；dto.py响应对象；db.py连接与事务；templates/static页面；scripts/init_demo.py合成账号初始化。新增功能沿用现有接口，不修改既有规则。所有测试使用隔离临时库，实际凭证不记录到输出。
