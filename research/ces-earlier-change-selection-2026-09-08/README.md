# 2024留存对2020—2022已知变化的选择诊断

从[报告](report.md)或[18行完整比较表](comparison.csv)开始。主目标是发布两波队列，三波文件仅用于后续成员识别。

本轮已看过2024结果，首次早期转移计算前另行固定[计划](analysis-plan.json)。不是结果盲态预注册，不重估2024政治效应。

Python 3.12，只有标准库。在本目录执行：

```powershell
python -X utf8 -B analyze.py --check
python -X utf8 -B write_report.py --check
python -X utf8 -B -m unittest discover -s . -p 'test_selection.py' -v
```

有官方原件时可完整复算，路径参数由使用者提供：

```powershell
python -X utf8 -B analyze.py --baseline '两波merged_recontact.csv路径' --selected '三波merged_recontact_2024_vv.csv路径' --check
```

原件SHA必须与[source-manifest.json](source-manifest.json)一致，错误即拒绝；`--check`只比较，不回写结果或改变mtime。省略`--check`会生成新结果。交付包不含微数据、受访者ID或凭据。权重仅来自两波文件的2022列。

文件说明：

- `cells.json`：每个固定群体、后续成员状态、结局及前后状态的匿名计数、权重矩和连接审计。
- `results.json`：18行分母、未加权和固定权重变化，以及6行留存减全体的差值。
- `comparison.csv`：完整宽表，包含方向人数、全部分母和权重比较。
- `denominators.csv`：资格、题目未知、权重子集与最终配对的分母。
- `transitions.csv`：完整状态表，包括不适用及未知。
- `transition_summary.py`：Muse分包代码，经Codex补充权重矩一致性校验。
- `analyze.py`、`write_report.py`、`test_selection.py`：Codex编写的读取、汇总、报告与独立合成验收。

只有匿名格表的离线复算不等于重新处理原始微数据，也不等于外部GitHub Actions通过。原件的独立监督复算证据见工作区`runs/run-279/independent-recount.json`；正式回执为`receipts/LH-262.receipt.json`。

所有结论限于描述已发布队列。无政治主体评价、选举预测、因果留存效应或对后期缺失结局的推断。
