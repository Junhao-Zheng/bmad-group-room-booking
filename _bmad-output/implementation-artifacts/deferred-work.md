
- source_spec: `3-3-revoke-block.md`
  summary: 全量回归暴露既有个人历史浏览器清理测试1秒启动预算不足，非3.3引入；转独立机械校正。
  evidence: 实验Y quality-review-fixes/python-all-parent.log中ready文件未创建；原脚本必须依次启动driver、wrapper与合成browser，未达故障注入前提。
