# 面板留存审计与2020年母样本入选构成

2026年9月8日。这是LH260面板报告之后的补充分析。已完成2020年度母样本到2024三波发布样本的跨阶段入选比较；真正的2022→2024两波留存分析仍待原件，当前不能称全部完成。

- [阅读新报告](report.md)
- [下载HTML](https://raw.githubusercontent.com/xukkx/us-midterm-study/main/research/ces-panel-retention-2026-09-08/report.html)
- [下载本轮复现包](https://raw.githubusercontent.com/xukkx/us-midterm-study/main/downloads/ces-panel-retention-2026-09-08.zip)
- [匿名计数](counts.json)、[完整结果](results.json)、[来源与下载状态](source-manifest.json)

## 当前结果的分母

2020年度原文件61,000人中6,175人进入2024三波发布文件。2020年拉美裔在业者为3,505人，其中282人进入三波；共和党倾向租房者为5,002人，其中401人进入三波。群体固定2020年，与上一轮实际就业及住房定义一致。三个锚点均由监督者独立从原件重数；所有6,175个ID唯一连接，七个基线字段无差异。

这是以2020年度完整文件为分母的入选比例，混合2022年邀请选择、调查完成、质量检查及2024年再次完成与质量检查。未进入三波不等于受邀拒访，不等于真实不投票，也不说明政治变化的选择偏差方向。

此次只用未加权人数。2024年权重不能用于未进入三波的人，也不能反推他们的政治结果。主计划固定3个人群、党派认同／就业／住房3个分层；加上总计共39行匿名计数。零人数保留，未知单列。输出比率分母少于80为null，80—99标low_n；底层计数不抑制。构成率以对应群体的母样本／入选／未入选人数为分母，入选率以对应类别的母样本人数为分母。

## 尚待取得的文件

[官方2020—2022面板V1.0](https://doi.org/10.7910/DVN/XV7ABM)采用CC0 1.0。官方文件页显示11,009行、1,332列，原CSV的MD5为`40b0d031dad46676cef9c7e0a31ab700`。这比三波代码本所述11,015人少6人，目前还没有解释。

请在[官方文件页](https://dataverse.harvard.edu/file.xhtml?fileId=10231930&version=1.0)选择 **Access File → Comma Separated Values (Original File Format)**。对应[官方原件下载入口](https://dataverse.harvard.edu/api/access/datafile/10231930?format=original)在本机请求返回403，页面按钮也未产生可读本地文件。原始文件未取得，网页行数不能算本地核验结果。

取得原件后应先复算MD5、确认列名、ID唯一性及两端差集，再逐项核对基线字段。当前没有用11,009作分母计算任何群体留存率，也没有把6人差异补成零。即使连接完成，仍需邀请、完成和质量检查标记才能区分各阶段原因。

## 复现

使用CPython3.12，只依赖标准库，从仓库根目录运行：

```text
python -B -m unittest discover -s research/ces-panel-retention-2026-09-08 -p test_retention.py
python -B research/ces-panel-retention-2026-09-08/reproduce.py --check
```

持有已核定的本地2020年度与三波CSV，可复算原始来源到匿名计数：

```text
python -B research/ces-panel-retention-2026-09-08/run_audit.py --baseline 本地/CES20_Common_OUTPUT_vv.csv --selected 本地/merged_recontact_2024_vv.csv --output research/ces-panel-retention-2026-09-08/counts.json --check
```

`run_audit.py`只接受两份已经固定SHA256的来源；它不自动接入两波文件。`retention_core.py`为纯计数函数，后续两波适配必须经过新的字段与来源核验。

`analysis-plan.json`固定原目标；在两波下载未成功且尚未计算母样本构成时，另行封印`fallback-plan.json`。`data-seal.json`固定本次匿名计数与来源信息。报告的三行主表由结果文件生成，ZIP内附逐文件哈希清单。

Muse1.3实际生成核心计数代码和报告初稿；Codex完成本地运行、缺ID与缺列检查修正、17项独立合成测试、三个锚点重算和发布。旧九模块、forward、LH259规则以及LH260文件保持不变。公开包不含个人原始记录、ID取值或内部执行日志。

本地HTML只做结构与内容检查，未执行浏览器视觉验收；远程Actions此前因账户账单锁定而未启动，不能把本地通过或工作流存在称为远程通过。
