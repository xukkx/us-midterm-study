# polls-vintage 账本 schema（LH-087）

来源：`data/raw/polls/raw_polls.csv`（LH-086 封印，SHA-256 `9f0b1855…f54756`，30 列 20466 行，1998–2023 全历史民调级数据集，许可 CC-BY-4.0）。账本 `data/processed/polls-vintage.jsonl`，逐民调一行，忠实转录零筛选。

## 字段

- 原始 30 字段原样保留（`poll_id`/`question_id`/`race_id` 为唯一键；`location` 地理；`type_simple` 竞选类型；`methodology` 访问模式；`samplesize` 样本量，允许来源自带的分数形态；`partisan`、`transparency_score`、`time_to_election` 等方法学字段；日期归一化为 ISO）。
- 新增：`available_at`（polldate 次日 00:00 UTC——发布不早于场次的保守近似）、`available_at_basis`、`lineage`（raw SHA-256 前缀 + 原始行号）、`schema_version`。

## 观测泛函映射（民调同化框架）

每行即一个观测泛函 y_i = ∫ w_i(x)·u(x, t_i) dx + b + ε：`location`+`type_simple` 决定空间支撑；`samplesize` 决定 Var(ε)；`pollster`（配合 `partisan`/`methodology`）承载 house effect b；`polldate` 决定 t_i。

## 泄漏铁律

`cand1_actual`、`cand2_actual`、`margin_actual` 为选举实际结果（逐行内嵌真值）。**任何消费本账本的模型只许将 `*_actual` 字段用作评分靶标，禁止作为特征**；违反即前视泄漏。

## 关键子集（对账 artifact 实测）

- `House-G-US`（全国 generic ballot，v1 全国场观测）：883 行。
- `Sen-G`（州级参院，v2 州场观测）：5006 行；中期届逐届 1998:171 / 2002:241 / 2006:408 / 2010:507 / 2014:459 / 2018:363 / 2022:419。
