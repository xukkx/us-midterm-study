# LH265匿名复现包

先读[报告](report.md)和[识别基础](foundations.md)。本包只有匿名频数、代码、计划、模型与报告。三波主目标为6,175名保留受访者；两波测量外界另以11,009人为目标。2024已看过，是回溯验证。

从该目录执行，Python 3.12，仅标准库：

```powershell
python -X utf8 -B -m unittest discover -s . -p test_dynamics.py
python -X utf8 -B experiments.py --check
python -X utf8 -B analyze.py --check
python -X utf8 -B report.py --check
python -X utf8 -B verify.py --check
```

`experiments.py --check`实际重做50个精确恢复和96个有限样本数据集，随后逐字节核验。`analyze.py --check`实际重训5种模型、整人五折和15个约束轮廓点；不只是读取已存估计。`verify.py`另以穷举公式检查概率、静态等价、CV、CSV和SHA。预计数分钟，无常驻进程。

如需生成全部结果，先去掉`experiments.py`的`--check`，再依次生成`analyze.py`、`verify.py`和`report.py`输出。版本化检查清单应在生成后重新制作，不能修改封印后直接宣称旧字节已通过。冻结结果以本包记录的Python 3.12环境为复现基准；未验证所有平台浮点实现。

本地原件连接复核（不包含在公开匿名复现依赖中）：

```powershell
python -X utf8 -B project.py --root D:/AI_Projects/longhorizon --check
```

要求官方两个CSV位于项目既有`midterm-model/data/raw/ces/`目录且SHA256匹配。原始CSV、连接键、逐人真值与账户日志不在包中。组成员固定于2020；“不确定”是合法回答，未当缺失或随机填补。

`analysis-plan.json`及其封印在模拟和真实拟合前建立，所有模型范围、种子、迭代上限与轮廓网格预先写定。弱测量模拟未收敛结果保留。拟合状态数3和4，发射共同而两个转移矩阵不同；另有静态类型、时变测量比较。满秩、拟合分数和模型内轮廓不证明心理或因果机制。

本地验证不替代GitHub执行器实际运行。公开PR为[us-midterm-study #1](https://github.com/xukkx/us-midterm-study/pull/1)；账户启动限制尚存时，远端测试没有运行。

外部理论来源及适用边界见[foundations.md](foundations.md)。变量题义沿用官方面板指南的既有人工核验，本轮另计算缺失；时间和构念限制见[indicator-inventory.json](indicator-inventory.json)。
