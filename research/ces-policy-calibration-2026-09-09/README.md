# LH267：政策限制的条件校准与嵌套历史

阅读[完整报告](report.md)、[数学补充](foundations.md)、[主张记录](claims.json)，或下载[匿名离线包](downloads/ces-policy-calibration.zip?raw=true)。仅Python 3.12标准库。

```text
python -X utf8 -B -m unittest discover -s . -p "test_*.py"
python -X utf8 -B simulate.py --check
python -X utf8 -B policy_calibration.py --check
python -X utf8 -B history_nested.py --check
python -X utf8 -B verify.py --check
python -X utf8 -B report.py --check
```

政策校准实际生成每题99,999个R1参考表与299,999个R2统计量，需要数分钟。种子、重复次数、比较家族、相对实质尺度和一个历史收缩参数已在新执行前封印；评审结果早已看过，不能称结果盲态注册。随机重复校准可以检查算法，不能产生新的经验受访者。

lh266-*为固定325ee0a来源的匿名结果/计数副本；reviewer-*为用户提供的探索评审计算，保留其单独身份。verify不导入生产置换/预测函数，另用精确超几何边际核定MI/TV零参考均值，以及全部训练折、预测、校准和路径贡献。输入不含逐人键。公开工作流另外重跑维护后的LH266完整程序，确认旧科学结果未变。

hypergeom_kernel.py来自一次实际OpenCode Go Meta Muse 1.3短内核分包，仅发送新规范与合成数据、工具全部禁用。实际完整消息、结束原因及用量已核验，独立穷举通过；摘要见execution-summary.json。其余计算与解释由监督端实施、核对。

新likelihood.py是维护后LH266 loglik的便携副本，私有维护回执核定函数AST相同。维数错误或正频数格零概率会明确拒绝，零计数格零概率合法；不再以数值下限改变所述似然。

区间均注明参考：置换的Monte Carlo区间只表示计算误差；R2同时区间另依赖组内Bernoulli假设；没有全国设计区间、机制概率或算法层面的预测CI。checksums.json记录本目录每个公开载荷，ZIP内部不把ZIP自身加入校验。
