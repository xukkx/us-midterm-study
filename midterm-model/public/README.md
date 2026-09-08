# 公开复现入口

这是2026年9月8日有效性更正的可独立执行部分。Python 3.11及以上，只用标准库，不联网、不需要凭据。

从仓库根目录运行：

```text
python -B -m unittest discover -s midterm-model/tests -p "test_*.py"
python -B midterm-model/public/reproduce.py --check
python -B research/validity-release-2026-09-08/verify_protocol.py
```

第二条命令从公开输入重算32组生态剖面、16组累计版投票记录审计、10组年度匹配审计及9个相邻届对分解，逐字节比较`outputs/tables.json`和`outputs/tables.md`。`--write`可重建。SHA-256、字节数、县年行数和连接覆盖在`inputs/manifest.json`；损坏输入会失败。

## 输入、来源与许可

|文件|内容与版本|来源和使用边界|
|---|---|---|
|county-input.csv|2012/16/20/24年12,452个县年；实际ACS vintage逐行保留|[MEDSL县级总统结果V20.0](https://doi.org/10.7910/DVN/VOQCHQ)，本地已封存元数据为CC0 1.0；[美国人口普查局ACS五年数据](https://www.census.gov/data/developers/data-sets/acs-5year.html)，政府公开统计。发布县级计数，不发布个人记录。|
|turnout-sufficient-statistics.json|累计CES中pid7=5—7，Own/Rent，2010—2024，按年龄格求和|[累计CES](https://doi.org/10.7910/DVN/II2DB6)，原输入SHA-256为543838b1116aa97e2e3e8976b9c5bf0224253233fa38757805b1cbff43db46ec，本地封存许可CC0 1.0。仅含16个聚合行。|
|decomposition.json|9个相邻届对的旧分解充分统计|同一累计CES；保留旧字段用于追溯，公开输出将persuasion解释为组内平均变化。|
|annual-turnout-sufficient.json|2016—2024五个年度CSV的10个聚合行、输入与代码本哈希|[CES官方下载入口](https://tischcollege.tufts.edu/research-faculty/research-centers/cooperative-election-study/data-downloads)。原年度文件不转载；公开的是计算出的群体计数和加权和。文件和版本差异必须根据内附哈希审查。|

县级输入来自既有总统票与ACS构成账本，以年份和五位FIPS内连接；共和、民主票数作两党分母。`hispanic/total_pop`及`hs_or_less/edu_total_25plus`分别作为人口构成。后者是25岁以上教育口径，不能直接解释为全体选民，更不能解释为全部工人。缺失的连接不补零；各年成功连接数量与票权重覆盖均公开。

公开命令覆盖“县级计数／调查充分统计→表格”的全过程。累计Feather清洗和早期候选人模型不在这条复现路径内；不宣称已实现原始微数据到所有历史结论的全链复现。年度原始CSV审计脚本`audit_annual.py`可供持有原文件的人重跑，输出应与内附充分统计一致；2016年CSV是此前从官方Stata文件导出的本地表示，重新下载不同表示时字节哈希可能不同，应记录转换而非绕过版本检查。

人口比例替代实际选民比例、供应商和权重变化、样本选择及匹配误差均不因程序通过而消失。无原始文件的干净检出只能验证公开充分统计之后的计算，不能独立验证微数据提取。

## 测试范围

`tests/`只保留随本公开包可执行的单元测试。首次公开版错误地混入了依赖未发布资产的测试：benchmark、real_benchmark、ingest、presidential_ingest、fec_ingest、senate_balancing_preregister、senate_joint_benchmark、senate_m0_benchmark。它们移到`integration-tests/`，原断言保留，依赖说明列在该目录；没有用“跳过”伪装通过。

新增测试检查生态界反例、异常输入、匹配编码、合法的“投票方法未知”、损坏文件、实证表行数和独立手算锚点。CI从GitHub的干净检出运行。它证明这一公开包可执行，不证明尚未完成的预测验证或因果主张。

本次公开文件只含源码、汇总表、说明和修订展示。原始个人数据、凭据、运行日志、内部合同与原有封存材料不发布。
