# LH264复现说明

从[报告](report.md)开始。Python 3.12，仅标准库；无逐人数据也可在本目录执行：

```powershell
python -X utf8 -B analyze.py --check
python -X utf8 -B structure.py --check
python -X utf8 -B report.py --check
python -X utf8 -B -m unittest discover -s . -p test_four_state.py
python -X utf8 -B dr_simulation.py --check
```

720次DR模拟均为合成数据。`structural-results.json`的不同潜在机制见证只在明示的测量误差族内成立，不能当作心理机制点估计或无假设锐界。

真实模型重训需两份与source-manifest.json一致的官方原件，并在本地受控目录保存投影：

```powershell
python -X utf8 -B project.py --baseline '两波CSV路径' --selected '三波CSV路径' --private '受控目录'
python -X utf8 -B analyze.py --fit --private '受控目录'
python -X utf8 -B analyze.py --score --private '受控目录'
python -X utf8 -B structure.py
python -X utf8 -B dr_simulation.py
python -X utf8 -B report.py
```

训练不会读取评分真值；预测和模型封存后才评分。不要将受控目录、哈希连接键、逐人H、真值或预测加入Git。公开匿名矩阵不能代替重新拟合真实模型。

`matrix4.py`是Muse实际交付并经独立数值验证的矩阵内核；其余结构映射、边界、数据投影与评估由Codex完成。旧LH263.1维修说明在原研究目录。完整回执与分包日志留在本地工作区。
