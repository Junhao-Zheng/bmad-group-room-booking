# Story 3.2 定向修补验证

本轮只执行覆盖改动的定向测试；全量、HTTP和其他浏览器回归留给父流程。原始初版证据 `docs/evidence/story-3.2/` 未覆盖。

- `node --test tests/test_blocks_js.cjs tests/test_rooms_js.cjs`：120项通过，无skip。本轮新增32项JS测试，包含两个真实脚本的双向身份事件及四类迟到响应，原53项room测试保留。
- `.venv/bin/python -m unittest tests.test_maintenance_block tests.test_maintenance_browser_runner -v`：17项通过，无skip。本轮新增3项存储保存性oracle测试；原14项maintenance测试移除未来功能的临时禁止断言，数量不变。
- `scripts.verify_maintenance_block_browser`：1280×800与390×844通过。run_id=`df9b7a8afe0b73d60bbfcfd270fa4b87`。原始报告、网络、截图与存储位于 `browser/`；实际使用已安装Google Chrome、独立临时库与私有凭证。
- 最终browser报告的应用/验证源码指纹与当前文件一致，8008端口已关闭。新存储断言确认全部原ID、每条原记录、全部原槽保存；另有2个新房间、4个新停用、6条新审计。

修补内容：不安全的浏览器room ID在发POST前拒绝，选项刷新拒绝不安全数字；房间/停用脚本仅传播AUTH_REQUIRED/FORBIDDEN页面事件，双向清列表、禁用控件、保存草稿与已确认成功，并阻止迟到成功重新显示数据；停用表单使用初始disabled fieldset与按钮，所有初始化完成后才启用，静态说明在未加载脚本时可见；未知结果清确认并要求重新核对；筛选变化清旧结果和计数；查询字段有错误文本/aria-invalid，恢复控件后才聚焦，日期max为9999-12-30。

验证增强：浏览器禁用JavaScript后强制点击创建按钮及Enter不导航/不发送带原因的URL；真实新增房间后点击刷新并核对三个选择器、完整草稿和确认重置；保存已提交但丢失响应的停用ID，查询与DOM逐项找回同一ID、起止及原因且无额外POST；预约/停用四态的DOM行数、标签、字段值与独立oracle完全比较。单元测试对空预约renderer和删除用途字段执行负向回归，确保验证会拒绝缺项。去除会禁止未来2.5/3.3正确实现的路由/函数/按钮缺席断言；未实现未来功能。

首次浏览器尝试在no-script阶段失败：对fieldset元素使用Playwright `isDisabled()` 的断言返回false。改为核对fieldset的原生disabled属性及实际子控件disabled状态后完整通过，生产代码未因此更改。失败报告与原始输出保留为 `browser/no-script-probe-failure.json`、`browser-no-script-probe-failure.txt`，未冒充通过。
