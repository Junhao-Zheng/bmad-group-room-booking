# PRD memlog 核对

日期：2026-11-12；Create headless，按调用方授权由代理完成核对，不冒充与人类逐条开会。

| 日志主题 | 落点或处置 |
|---|---|
| 配置解析、工作目录、headless 与唯一正文 | `resolved-*.json`、PRD frontmatter、相对 `prd.md` 链接及 `review-preparation.md` |
| 用户确认边界、H-01—H-11、实验 A/B | PRD §0/1/3/7/8 与 addendum 课程边界；未把 AI 规则计作人类决定 |
| A-01 停用时段与撤销 | BR-04、FR-18/19/20；R-03 补充事实与时间状态后保持同一范围 |
| A-02 容量降低保护 | BR-05、FR-10/17、NFR-01；进行中与未来记录均受保护 |
| A-03 可见性与历史 | BR-06、FR-07/13/20/21、NFR-02；真实保留期限转 OQ-03 |
| A-04/05 账号及会话 | FR-01/03、NFR-02；账号管理网页范围外 |
| A-06 输入上限 | FR-08/16；共享原因上限明确，非真实使用规模 |
| A-07/08 幂等及取消 | FR-12/14/15/19、NFR-01；R-02 补充规范化字段，未扩展新能力 |
| 冻结编号与需求验收 | 22 FR、4 NFR、3 UJ；`mechanical-check.json` 核对编号与本地链接 |
| 输入核对与独立评审修订 | `reconcile-*.md`、原始 `review-rubric.md` 和 `review-resolution.md` |
| 结构、语言及课程状态同步 | `review-editorial.md`、字数证据、course-scope 的 PRD 状态行与说明段 |
| 未知真实使用与长期运维 | OQ-01—OQ-03 已指定项目维护者及复核条件；不阻塞原型架构，不把未知值捏造为事实 |

无被静默丢弃的需求决定；不适合 PRD 的实现机制留给下游，过程信息留在阶段证据。所有 audit/override 信息写入 memlog，不放入 addendum。外部 handoff 和 on_complete 配置为空，无需调用外部服务。
