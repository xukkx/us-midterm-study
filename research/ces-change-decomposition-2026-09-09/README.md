# LH268 观测变化评分分解与单一政策挑战者

本目录是 LH-302/run319 的中文、可离线复算研究包。先阅读 [foundations.md](foundations.md) 与 [report.md](report.md)，再运行：

```text
python -X utf8 -B -m unittest discover -s . -p "test_*.py"
python -X utf8 -B verify.py --check
python -X utf8 -B r1_sensitivity.py --check
python -X utf8 -B challenger.py --check
python -X utf8 -B report.py --check
```

`joint-counts.json` 只有匿名联合格、raw8边际与五折计数；原始 CES 逐人文件不在本包。`project_raw.py` 的投影模式仅限授权本地原件，公开 `--check` 不读取原件。
