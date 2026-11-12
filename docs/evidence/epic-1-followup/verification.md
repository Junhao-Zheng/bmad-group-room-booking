# 第一个史诗复盘修补的实际验证

2026-11-12执行，合成数据，父流程直接实现（独立实现通道3次传输失败）。初次通过：Python106项、JavaScript53项，0skip；原始输出为[Python](python-tests.txt)、[JavaScript](javascript-tests.txt)。

[相反父环境HTTP](auth-http-opposite-parent.json)以`COOKIE_SECURE=true TRUSTED_HOSTS=invalid.invalid`启动验证器，验证器使用私有临时库及显式loopback HTTP配置；实际PASS。

[浏览器报告](browser/browser-results.json)：1280×800、390×844，真实登录/退出、共享查询、可用卡片、预约/重放；19个应用文件、4个验证源文件与30张截图SHA256已独立重算一致。[个人历史回归](history/browser-results.json)亦通过，业务表/槽/审计读取前后不变。

R1—R4对应测试与实际行为详见[工作项](../../../_bmad-output/implementation-artifacts/epic-1-followup.md)。浏览器只使用临时凭证，不连接用户个人浏览器配置。旧故事、旧测试及旧截图保留。

## 最终评审后验证

- 全量Python108项，原始[日志](reviewed/python-tests.txt)；JavaScript54项，原始[日志](final/javascript-tests.txt)，均无skip。最后仅调整日程焦点的直接条件，JS全量及两浏览器已重跑；Python覆盖代码未再变更。
- 最终[认证/查询/预约/重放](final/browser/browser-results.json)run_id=`1fd175105a64e9db6b03a61c1d59b2c1`，1280×800和390×844均PASS；实际Node/Playwright路径/Chrome版本及规范化参数随报告。最终app/runner及全部截图SHA重新计算一致。
- 最终[个人历史](final/history/browser-results.json)run_id=`59a3271f9514c7c989fe8e2d9fbac58c`，两视口PASS，业务/槽/审计不变；源码指纹与当前工作树一致。
- [相反父配置HTTP](reviewed/auth-http-opposite-parent.json)保存实际父配置及有效子配置；同一场景也进入108项Python测试。
- [源码保护变异](final/source-guard-mutation.txt)故意禁用guard后测试失败，符合预期；正常、未变更控制PASS。
- 初次及修补中间输出完整保留，包括reviewed/javascript-tests.txt的4项失败；不覆盖为最终通过。
- [独立评审](../reviews/epic-1-followup-review.md)11条，9修补、2low拒绝，0defer。
