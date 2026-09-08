# 两波发布样本到三波发布样本的保留情况

2026年9月8日。用户补充的原始CSV已核验并接入，补齐同日早期报告尚缺的两波到三波分析。原分析计划在本文件取得前已经固定，本次沿用原群体与分层，不修改旧结果。

- [阅读报告](report.md)
- [下载完整复现包](https://raw.githubusercontent.com/xukkx/us-midterm-study/main/downloads/ces-panel-two-wave-retention.zip)
- [来源、版本和哈希](source-manifest.json)、[连接审计](link-audit.json)
- [39行匿名人数](counts.json)、[156个比率与各自分母](results.json)
- [事前分析计划](../analysis-plan.json)、[原计划封印](../plan-seal.json)

全部人群为11,009→6,175；2020年拉美裔在业者584→282；2020年共和党倾向租房者749→401。群体固定在2020年，不能解释为2024年当前在业者或租房者。党派、就业和住房基线分层包含零人数与未知类别。

比率的分母是出现在2022两波发布文件中的人，不是完整邀请框。未进入三波文件可能涉及多个阶段，缺少过程标记时不能归为拒访或没有投票。输出比率分母少于80为null，80—99标low_n，底层人数不改。字段inclusion在本增补中表示两波到三波的条件保留；三个composition字段分别表示各群体在两波、三波及未进入三波样本中的基线构成。所有结果未加权。

两波来源为[官方数据集V1.0，CC0 1.0](https://doi.org/10.7910/DVN/XV7ABM)，fileId10231930。原CSV实际11,009行、1,332列，MD5与官方完整值40b0d031dad46676cef9c7e0a31ab700相同。三波V2.0有6,175人，均唯一连接至两波文件，七个2020字段和2022连接键零差异。指南11,015人与实际文件差6人的原因仍未知；指南2022年完成数减质量剔除数与文字最终人数另差3人。这些来源差异没有被填零或归为未回应。

使用CPython 3.12，仅标准库。从仓库根目录，或ZIP解压后的根目录运行：

```text
python -B -m unittest discover -s research/ces-panel-retention-2026-09-08/two-wave -p test_two_wave.py
python -B research/ces-panel-retention-2026-09-08/two-wave/reproduce.py --check
```

ZIP同时包含上一级冻结的计数、比率函数及计划，因而解压后可以离线复算，不需要个人CSV。上一级历史reproduce.py仍核验当时的2020年度入选构成，末行“尚未计算”是该历史包的状态；新结果请使用本目录reproduce.py。

若自行取得两个官方原CSV，可从原件完整重算；下列路径仅为本机示例，公开仓库不包含原件：

```text
python -B research/ces-panel-retention-2026-09-08/two-wave/two_wave.py --baseline midterm-model/data/raw/ces/panel-2020-2022/merged_recontact.csv --selected midterm-model/data/raw/ces/panel-2020-2024/merged_recontact_2024_vv.csv --counts research/ces-panel-retention-2026-09-08/two-wave/counts.json --results research/ces-panel-retention-2026-09-08/two-wave/results.json --check
```

程序先核对两个固定SHA256，再检查CSV结构、两个年份连接键、集合包含关系及七项基线一致性。--check只比较字节，不改写结果。data-seal.json锁定来源、连接审计与匿名人数；它是结果数据封印，不能代替先前已有的分析计划封印。

下一步先核实邀请、完成、质量检查记录和来源版本差异，再为无法观测的政治结果制定独立的敏感性分析计划。本次没有重估政治转移、提供2026胜负预测或消除未观测选择。
