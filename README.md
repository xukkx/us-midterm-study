# 美国中期选举研究

## 当前阅读入口

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
