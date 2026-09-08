# CES 2020—2024面板：同人变化与证据边界

2026年9月8日。本轮已完成来源核验、分析前登记、实际计算和独立复核。

- [先读研究报告](report.md)
- [下载HTML阅读版](https://raw.githubusercontent.com/xukkx/us-midterm-study/main/research/ces-panel-2020-2024/report.html)
- [下载本轮完整复现包ZIP](https://raw.githubusercontent.com/xukkx/us-midterm-study/main/downloads/ces-panel-2020-2024.zip)
- [结果JSON](results.json)、[数字追溯](report-trace.json)、[变量与代码本页码](variable_map.json)

6175名三波留存者中，2020年拉美裔在业者282人；两届总统票的有效配对154人，权重有效n约59.6。仅观察到1人D→R、1人R→D。不能从这一样本推断2026年哪党控制国会。

## 数据与固定比较

[官方来源V2.0](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/CETPVT&version=2.0)，DOI `10.7910/DVN/CETPVT`，CC0 1.0。CSV为6175行、2229列；CSV、DTA、181页PDF三个成员的完整MD5与官方文件页一致，并固定SHA-256。[完整来源](source_manifest.json)、[实际核验](source-verification.json)、[2020年字段交叉核对](baseline-source-audit.json)。原始微数据由读者从官方来源自行获取，本包不包含个人记录。

2020年、2022年、2024年ID各自唯一且无缺失；官方合并行提供同人关系，不要求三列ID数值相等。全部2020年ID连回年度文件，七个核对字段无差异；这只核实来源，不提供未回访者的邀请框。

[分析计划](analysis_plan.json)和[变量映射](variable_map.json)在读取转移结果前，于2026-09-08 09:03:48 UTC封印。人群固定2020年：全体；pid7为5—7且租房者；族裔为拉美裔（race=3或hispanic=1）且全职／兼职就业者。后者不等于工人阶级，也不代表2020年后所有新增拉美裔选民。

总统票比较2020与2024，众院票和党派认同分别作三波两两比较。议题只取可比的全民医保、药价谈判及有条件合法化，不按相同变量后缀强拼题目。所有未知、未参加选后、题目缺失及档案无匹配状态保留在完整矩阵。

总统／众院主比较用`commonpostweight_24`，其他主比较用`commonweight_24`。2020→2022选票比较也使用同一2024年选后权重，因此只代表对应留存选后样本。`vvweight_22`及`vvweight_post_22`是2022年登记选民目标的另一套结果；后者不是2024年选后完成权重，两种目标不能混称成人样本稳健性。

输出比率、均值、变化及区间按正权重有效分母n抑制：n<80为null，80—99标记low_n。原始人数、权重有效n和充分统计不抑制。方向率以该方向起点且两端有效者为分母；矩阵份额以全组正权重者为分母。两党认同比较排除独立派，但完整矩阵保留独立派。

权重有效n为`W²/W2`。精度诊断为固定权重配对差值的线性化标准误，`SE² = n/(n−1) × Σ w²(d−均值)² / W²`，区间使用均值±1.96SE。它不是完整调查设计区间，不包含流失、匹配或测量偏差，稀少变化事件会使正态近似脆弱。三波持续性中5项分母不足80，1项因基线群体定义不适用，均不发布比率。

## 离线复现

使用CPython 3.12、仅标准库，从仓库根目录执行。匿名账本2696行，生成114项比较（57项主比较及57项登记选民目标比较）、12行权重覆盖、9行投票档案覆盖及6项持续性记录。

```text
python -B -m unittest discover -s research/ces-panel-2020-2024 -p test_panel.py
python -B research/ces-panel-2020-2024/reproduce.py --check
```

持有已核定官方CSV时，可再检验原件到匿名账本的全链一致性；此命令只在本地读取原件，不输出个人行：

```text
python -B research/ces-panel-2020-2024/reproduce.py --check --raw-csv 本地路径/merged_recontact_2024_vv.csv
python -B research/ces-panel-2020-2024/verify_source.py --raw-dir 本地三个文件所在目录
```

运行器先校验分析封印与数据封印，再逐字节核对结果。ZIP内的`bundle-manifest.json`记录每个成员的SHA-256。公开包可以离线复现聚合统计到结果；官方原件重新下载和年度基线交叉核对，需要读者另行取得相应原文件。

## 已核验与尚未解决

OpenCode Go的Muse 1.3实际生成变量与计划草稿、核心代码、统计代码、汇总代码和报告初稿。模型只收到经批准的字段、代码本和汇总信息，全部工具禁用。Codex完成本地执行、编码与分母修正、18项独立合成测试、三个头条数的原始CSV独立重算和最终编辑。中途有附件截断、无输出及超时尝试，未当作成功交付；测试由Codex编写。

本轮本地面板测试及原始CSV→匿名账本→结果逐字节复算通过。远程Actions此前因账户账单锁定而未启动；工作流配置存在不等于远程通过。本地HTML仅完成内容与结构检查，浏览器视觉验收受本地URL策略限制。

仍缺少2022年邀请框与未回访者资料，分群流失率未知；代码本2022年完成、剔除与保留数相差3人，保留原文并记录。早年2010／2012／2014原始年度文件待补，前瞻输入与预测尚未冻结，选后计分另需批准。九个旧模块及旧forward封印保持原样。
