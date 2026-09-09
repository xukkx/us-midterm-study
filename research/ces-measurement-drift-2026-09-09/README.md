# LH266：测量漂移、政策轨迹与历史基准

阅读[报告](report.md)、[数学基础](foundations.md)、[主张记录](claims.json)。下载[匿名离线复现包](downloads/ces-measurement-drift.zip?raw=true)。Python 3.12，仅标准库；无账号、原始逐人记录或外部服务要求。

在本目录运行：

```text
python -X utf8 -B -m unittest discover -s . -p "test_*.py"
python -X utf8 -B equivalence.py --check
python -X utf8 -B profile.py --check
python -X utf8 -B policy.py --check
python -X utf8 -B history.py --check
python -X utf8 -B verify.py --check
python -X utf8 -B report.py --check
```

profile实际重跑全部有界搜索，需要数分钟；其他命令较快。verify独立枚举隐态，不导入拟合、等价路径或预测实现。检查输出为确定性JSON/CSV/Markdown，最后位浮点重现基于Python 3.12；科学约束另使用记录的数值容差核验。checksums.json封存每个公开载荷，ZIP不把自身纳入内部摘要。

joint-trajectories.json含三项分别的PID4×政策三波匿名联合人数、原八码与同人五折整数表，保留政策未知。lh265-source.json保留原拟合参数、计数、旧五折分数和源SHA；没有重新发布原始CES。拥有原件者可在仓库根目录运行project.py --root <根目录> --check核定源SHA与全部投影；该私有输入路径不属于公开工作流。

原件来源与时点证据见timing-audit.json；指南的精确题目时间不足，未作同时或滞后因果解释。analysis-plan及policy-restrictions各带计算前封印，前者已看LH265与评审结果，后者在新政策联合表读取前补充细则；都不是结果盲态注册。

数值状态严格区分：合法见证、有限局部搜索端点、未找到见证、非法概率参数。所有全局认证字段为false；两个拟合损失容差均非95%区间。行政合同编号因并行任务冲突另行迁移，不改变已封印科学计划。
