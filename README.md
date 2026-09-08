# 美国中期选举研究

## 当前阅读入口

- [研究有效性更正与下一步方向（2026年9月8日）](midterm-model/docs/validity-corrections.md)
- [可复现表：生态界、投票记录与档案匹配、变化分解](midterm-model/public/outputs/tables.md)
- [同人面板资料与当前阻塞](research/validity-release-2026-09-08/panel-feasibility.md)
- [独立前瞻验证协议](research/validity-release-2026-09-08/prospective-protocol.md)
- [公开执行范围和命令](midterm-model/public/README.md)

本次更正撤回了“同人转换”“不可逆底线”“租房者退出”和“资金不是瓶颈”等超出证据的解释。众院未经验证的席位点估计已经从仪表盘主要展示撤下。旧版本可从Git历史查看，原始计算与封存研究未改。

```text
python -B -m unittest discover -s midterm-model/tests -p "test_*.py"
python -B midterm-model/public/reproduce.py --check
python -B research/validity-release-2026-09-08/verify_protocol.py
```

公开包包含标准库源码、可独立运行的测试、公共说明和县级／调查聚合输入。默认测试不再混入依赖未公开配置和原始文件的8个集成测试；其原断言与依赖清单位于`midterm-model/integration-tests/`。

三波面板尚未下载成功，前瞻协议尚未完成输入与预测冻结。本仓库不据此宣布2026年国会控制权，也不把程序通过等同于因果识别。

不发布个人微数据、凭据、内部合同、运行日志及原有封存材料。来源与许可按各文件说明保留。
