# LH-263复现说明

先阅读[报告](report.md)。两个主要交付是[识别表](identification.csv)和[遮蔽校准比较](benchmark-comparison.csv)。

Python 3.12，仅标准库。以下命令在本目录执行，不需要原始微数据或联网：

```powershell
python -X utf8 -B identify.py --check
python -X utf8 -B anonymous_benchmark.py
python -X utf8 -B report.py --check
python -X utf8 -B -m unittest discover -s . -p 'test_methods.py' -v
python -X utf8 -B simulate.py --check
```

匿名包可以复算36个识别目标、12个嵌套对比、48组端点见证、9个矩阵恢复结果及600次合成模拟。它不包含真实模型重训所需的逐人2020协变量，也不能凭匿名矩阵重构实际受访者。

如需从官方原件重新训练，先取得与`source-manifest.json`哈希一致的两波和三波CSV，在非同步本地目录执行。下列命令会写本目录的新增LH263产物；不对LH262运行：

```powershell
python -X utf8 -B project.py --baseline '两波CSV路径' --selected '三波CSV路径' --private '本地受控投影目录'
python -X utf8 -B identify.py
python -X utf8 -B benchmark.py --input '本地受控投影目录/masked-input.jsonl' --private '本地受控投影目录'
python -X utf8 -B evaluate.py --private '本地受控投影目录'
python -X utf8 -B anonymous_benchmark.py --private '本地受控投影目录'
python -X utf8 -B simulate.py
python -X utf8 -B report.py
```

`benchmark.py`不接收评分真值路径，S=0的训练结局必须为null；`evaluate.py`先检查预测／模型封印，再读取单独真值。投影中的哈希键仍是受控连接信息，不得纳入分享包。不要用真实模型的参数或评分结果反向改变已固定的变量和超参数。

关键文件：

- `analysis-plan.json`、`analysis-plan-seal.json`：已看过旧结果之后、运行前指定的本轮口径，不是盲态预注册。
- `pid-atoms.json`：互斥群体成员×S×原始PID类型的匿名格；保留群体重叠。
- `identification-results.json`、`endpoint-witnesses.json`：两种明确不同的分类目标、固定权重与未加权界限及见证。
- `benchmark-results.json`、`benchmark-sufficient.json`：恢复、方向、重叠、固定拟合后单人影响、MNAR场景与匿名矩阵充分统计。
- `model-fit.json`、`predictions-seal.json`、`unmask-audit.json`：公开式模型参数与阶段哈希；不含逐人预测和真值。
- `simulation-results.json`、`simulation-ledger.json`：合成DGP推断检查；不是真实选民或新增经验数据。
- `bounds_kernel.py`、`glm.py`：Muse分包生成，经过监督者检查与修订。
- `linear_bounds.py`：小型有界实数LP／正分母线性分式优化；不把实数多面体自动等同于有限整数队列。

本轮未安装NumPy，也未升级用户包中的探索性贝叶斯示范为新模型。没有Git、公开发布或外部CI通过声明。完整本地执行证据在工作区`runs/run-280/`，正式回执为`receipts/LH-263.receipt.json`。
