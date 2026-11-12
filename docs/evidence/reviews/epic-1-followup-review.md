# Epic 1 完成后修补评审

初始差异基线d545ca5；三层全部发起后收齐再分类。Blind 10条，edge返回[]，verification 1条，共11条；9条直接修补、2条low拒绝，无defer。验证层首次上下文连续2次传输失败，新的独立上下文返回；共4个评审上下文、2次失败调用，不将失败计通过。

| 来源 | 判定 | 处置与核对依据 |
| --- | --- | --- |
| B1 | medium | patch：rooms响应及空列表确少严格envelope类型，Python相等会吞1/1.0；补独立ok/items/total断言，不改正确DTO实现。 |
| B2 | medium | patch：两个block原因相同确掩盖跨记录串值；浏览器专用夹具108采用不同原因，逐卡断言。 |
| B3 | low | reject：当前受控driver只在两视口全部断言通过后输出PASS；非零退出已拒绝，FAIL+空results须替换内部run_browser才产生。无当前正常调用者会产生该报告；增加第二套场景协议校验复杂度不属于日常缺陷直接修正。 |
| B4 | low | reject：真实driver的page.screenshot成功后才继续，异常必非零退出；任意坏字节文件须替换受控driver或外部篡改。现有SHA绑定与父流程视觉检查覆盖本轮产物；另写PNG解码和逐场景清单校验不为此低概率条件增加复杂度。 |
| B5 | low | patch：Node模块搜索可能被更近node_modules遮蔽；driver返回实际require.resolve路径/版本，launcher比较与请求安装路径一致。 |
| B6 | low | patch：增加实际Node版本、实际浏览器路径、规范化scenario与输入参数；不记录临时凭证参数。 |
| B7 | medium | patch：原mock只检查比较分支，不能发现真实hash函数漏文件；新增临时树实测app编辑/增加/删除及每个helper变化。 |
| B8 | low | patch：原调用已在验证文档说明，但JSON确未绑定父/子配置；仅记录两个无秘密配置项及child origin，并新增真实相反父环境HTTP回归。 |
| B9 | medium | patch：原超时测试字段无值/直接空payload不能证实值保留；改为实际submit处理器，验证请求和最终两字段值。 |
| B10 | medium | patch：等待时其他表单仍可输入，原成功无条件focus会打断；仅当焦点仍在本查询/反馈或body时恢复，真实双视口延迟响应保持另一表单焦点。 |
| V1 | medium | patch：预验证证明原source-change测试被缺截图错误误通过；同一含图片fixture的未变化控制必须PASS，变化必须INCOMPLETE，禁用guard后的变异实测失败。 |

实现通道原3次调用均传输失败、无产物。父流程直接实现，评审修补亦由父流程完成；不冒充新代理输出。修补期间4项JS焦点回归先失败：成功前焦点停在本查询旧反馈上，应恢复按钮；补入本查询feedback条件后通过，保留失败原输出。原初次故事指标不覆盖。

最终验证见[证据](../epic-1-followup/verification.md)。本次业务规则、FR/ADR合同不变；没有把验证缺口直接算成已发生的ADR或project-context实现冲突。
