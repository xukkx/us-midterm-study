# LH271 交回摘要

管理合同 LH-306／run-323；分包登记 LH-307—LH-311。本轮已完成固定测量审计、描述核算和三套调查加权关联模型，未发布或使用 Git。

- 原件：ANES 2024，2026-05-19版，5,521条、键唯一；新非纸笔样本3,105人。
- 选后设计框2,694人；共同完整应答域1,835人；固定共同支持S为793人。
- 主关联差中差 −0.002730 个百分点；条件性95%区间 [−3.400832, +3.395372] 个百分点。没有明确交互方向，不能称为因果或身份无效。
- 来源、编码、权重与11自由度控制项：`measurement_manifest.json`、`analysis-spec.json`、`source-excerpts/`。
- 表与结果：`denominator_and_material_identity_tables.csv`、`diagnostics.json`、`associational_results.json`；系数只作审计附件，不比较“阶级/文化重要性”。
- 完整说明：`report.md`、`identification_and_claims.md`。两次科学检查附JSON。
- 验证：原件独立编码、578行表、793个标准化点值，16项计划护栏、7项分析测试、2项完整性测试。完整测试的实际日志见执行目录。
- 模型：12次调用、3次重试；Go的DeepSeek与Muse各两次失败，Ollama GLM5.3两次截断。Flash资格答案通过，T2/T3经修订采用，T1部分不可靠、T4截断、T5模板错误均明确记录。
- 费用：已报告输入1,491与生成14,619 tokens；实际API金额、订阅用量和协调者用量未核实，保持未知。没有购买额度。

复核命令（工作目录为项目根）：

```text
python research/anes-class-identity-2026-09-11/check_package.py
python -m unittest discover -s research/anes-class-identity-2026-09-11 -p test_*.py -v
python -m unittest discover -s runs/run-323/plan -p test_guardrails.py -v
```

公开式摘要包不含问卷逐人记录、标识符、凭证或私有预测行。完整原件复算需要本地 `runs/run-323/sources/data.csv`；不能将摘要包称作无需原件即可重做全部拟合。

仍待科学判断：POST身份的方向、未应答选择、S覆盖之外的推广，以及需要什么独立的选前利益／可信度测量。白人／黑人身份题的完整资格分母不可重建，限有效应答者描述。LH270原定最终科学审核状态不变。
