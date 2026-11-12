# PRD 结构与语言检查

本文件帮助课程评审者、架构与实现代理准确理解并引用需求基线。依据 `bmad-prd` 的 `doc_standards` 显式指令，应用 `bmad-review lenses=structure,prose`，结构先于语言；reader_type 为 humans，默认样式为 Microsoft Writing Style Guide，不改变业务含义。

按 Strategic/Context (Pyramid) 模型检查：用途、证据边界、目标和范围先行，继以术语、统一规则、分组能力和验收证据；未出现要求读者先读实现细节才能理解需求的倒置。跨能力规则集中在 BR，FR 保留可单独提取的验证后果。`addendum.md` 只保存下游设计注意和取舍，没有偷偷固定数据库、框架或锁。

使用技能 `word_metrics.py` 实际计数（中文按脚本口径）：修订后、polish 前 PRD 8,401 words，addendum 793 words；分节计数存于 `word-metrics-*-pre-polish.json`，不是估计页数。

| Pass | Original Text | Revised Text | Changes |
|---|---|---|---|
| structure | PRD §3“术语与统一业务规则”，1,236 words | PRESERVE | 统一时间、占用、历史和隐私语义，FR 可引用且保持稳定；删去会增加规则分散，不建议压缩。结构节省 0 words |
| structure | addendum“课程流程边界”，122 words | PRESERVE | 下游独立读取时仍需知道实验隔离与真实门禁边界；与正文的有限重复用于防止错误归因，结构节省 0 words |
| prose | “初始化后的存储不得出现可恢复明文口令” | “初始化后的存储不得出现明文口令或可逆加密口令” | 以明确对象替换含糊修饰，保留必须使用口令哈希的原意；已采纳 |

结构无需修改，0 条删改建议、2 条保留说明；预估结构减少 0 words（0%），无字数上限，保留边界例子以保证理解。语言只有 1 项实质措辞澄清；其他段落保留直接、可测的中文需求语气，无额外风格改写。addendum 语言检查无修改建议。

本检查发生在输入核对和独立 rubric 修订之后。最终计数见 `word-metrics-prd.json` 与 `word-metrics-addendum.json`；这是文档检查，不是功能或 NFR 测试通过证据。
