# 美国中期选举研究

## 当前阅读入口

- [最新LH265：三波潜在动态与测量稳定性](research/ces-three-wave-dynamics-2026-09-09/report.md)
- [LH265识别基础与跨模型等价](research/ces-three-wave-dynamics-2026-09-09/foundations.md)
- [下载LH265匿名复现包](research/ces-three-wave-dynamics-2026-09-09/downloads/ces-three-wave-dynamics.zip?raw=true)

LH265已完成6,175人三波实际拟合、50组精确恢复、96次有限样本恢复和整人五折比较。共同测量HMM给出条件潜变化，但静态时变测量可精确复制其观察分布；心理机制尚不能跨模型确定。

- [最新LH264：四状态与潜在机制识别](research/ces-four-state-mechanisms-2026-09-08/report.md)
- [下载LH264匿名复现包](research/ces-four-state-mechanisms-2026-09-08/downloads/ces-four-state-mechanisms.zip?raw=true)
- [LH263.1安全接口维修](research/ces-identification-calibration-2026-09-08/MAINTENANCE.md)

LH264以全部11,009人的字面四状态为主要描述目标，并用实际观测等价见证区分已识别回答转换与未识别的潜在测量机制。维修保持原实证结果；新增错设模拟分别检查点偏差与区间覆盖，不把模型拟合视为心理或因果机制已被证明。


- [最新：PID识别界限与遮蔽结局校准（LH263）](research/ces-identification-calibration-2026-09-08/report.md)
- [下载LH263代码、报告与匿名结果](research/ces-identification-calibration-2026-09-08/downloads/ces-identification-calibration.zip?raw=true)
- [早期政治变化是否受后续留存影响（LH262）](research/ces-earlier-change-selection-2026-09-08/report.md)
- [LH263离线复现说明](research/ces-identification-calibration-2026-09-08/README.md)

LH263区分不确定回答与真正空缺、完成分类与字面响应目标。三种固定方法的遮蔽校准保留了子组恢复失败；它是已看旧结果后的回溯诊断，不能证明2024可迁移性。真实模型重新训练需要本地官方原件。研究目录中的历史回执和完整运行记录引用指向原本地工作区；本公开仓库不包含这些内部文件。


- [最新增补：两波到三波的样本保留](research/ces-panel-retention-2026-09-08/two-wave/report.md)
- [下载两波留存复现包](downloads/ces-panel-two-wave-retention.zip?raw=true)

- [最新增补：哪些人进入了三波面板](research/ces-panel-retention-2026-09-08/report.md)
- [下载入选构成复现包](downloads/ces-panel-retention-2026-09-08.zip?raw=true)

- [同一批人变了什么：新面板报告与研究方向](research/ces-panel-2020-2024/report.md)
- [下载本轮报告、源码与匿名统计ZIP](downloads/ces-panel-2020-2024.zip?raw=true)

- [研究有效性更正与下一步方向（2026年9月8日）](midterm-model/docs/validity-corrections.md)
- [可复现表：生态界、投票记录与档案匹配、变化分解](midterm-model/public/outputs/tables.md)
- [同人面板资料与当前进展](research/validity-release-2026-09-08/panel-feasibility.md)
- [独立前瞻验证协议](research/validity-release-2026-09-08/prospective-protocol.md)
- [公开执行范围和命令](midterm-model/public/README.md)

本次更正撤回了“同人转换”“不可逆底线”“租房者退出”和“资金不是瓶颈”等超出证据的解释。众院未经验证的席位点估计已经从仪表盘主要展示撤下。旧版本可从Git历史查看，原始计算与封存研究未改。

```text
python -B -m unittest discover -s midterm-model/tests -p "test_*.py"
python -B midterm-model/public/reproduce.py --check
python -B research/validity-release-2026-09-08/verify_protocol.py
python -B -m unittest discover -s research/ces-panel-2020-2024 -p test_panel.py
python -B research/ces-panel-2020-2024/reproduce.py --check
```

公开包包含标准库源码、可独立运行的测试、公共说明和县级／调查聚合输入。默认测试不再混入依赖未公开配置和原始文件的8个集成测试；其原断言与依赖清单位于`midterm-model/integration-tests/`。

三波面板已核验并完成同人变化分析，拉美裔在业者总统票有效配对154人、权重有效n约60；前瞻协议尚未完成输入与预测冻结。本仓库不据此宣布2026年国会控制权，也不把程序通过等同于因果识别。

不发布个人微数据、凭据、内部合同、运行日志及原有封存材料。来源与许可按各文件说明保留。
