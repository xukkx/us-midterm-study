# 美国中期选举结构—概率模型研究纲领

## 1. 研究边界

本项目把原始提案视为一组待证伪的研究假设，而不是一份可直接上线的模型规格。第 0 层只建设测量、时间切分、概率评分和最小基线。每个新增组件必须先说明它作用于哪一层，再接受与该职责匹配的样本外基准；没有独立检验目标的组件不进入实现队列。

本轮严格遵守以下边界：

- `synthetic_only=true`。全部基准数据均为固定种子的确定性合成数据。
- 合成结果只能证明实现和验证闸按预期工作，不能证明现实选举预测有效。
- 不生成、暗示或反推任何 2026 年胜率、席位预测或多数党概率。
- 不联网，不引入第三方依赖，不把当前网页、修订后经济数据或事后评级冒充历史时点信息。
- 没有真实历史逐届滚动样本外证据的组件不得标为 `retained`。

依赖顺序如下：

```text
目标与规则合同
  → 点时数据与泄漏审计
  → expanding-window rolling-origin 切分
  → proper score 评分尺
  → House / Senate 各自的 M0
  → House / Senate 各自的 B1
  → 各院相关席位模拟
  → 真实历史数据接入
  → 局部结构、轮询、候选人和投票率组件
  → 最后才检验两院共享潜在环境与联合模拟
```

## 2. 预测目标必须先于模型固定

### 2.1 House 目标

House 是 435 个同时进行、受地图约束的选举。当前席位分割只提供任职者和席位暴露背景；正式预测必须逐席生成结果后求和，不能在当前席位数上机械加减一个全国摆动。

每个 House 竞选至少需要以下身份：

- `cycle`
- `office=HOUSE`
- `state`
- `district`
- `race_id`
- `election_stage`
- `map_id`
- `forecast_as_of`

竞选级目标分为两类：

- 所有席位均可定义的党派胜负；
- 仅在口径成立时定义的民主党两党得票边际。

无人竞争、排序选择、决选或第三党显著介入的比赛不得被静默删除。若连续边际目标不成立，须显式标记缺失原因，但席位胜负仍必须进入议院模拟。

### 2.2 Senate 目标

Senate 不是缩小版 House。每届只暴露特定席位类别，且控制权还取决于未改选席位、独立议员的党团归属和副总统破平票规则。唯一竞选身份至少还要包含：

- `senate_class`
- `is_special_election`
- `seat_term_end`
- `caucus_mapping`
- `runoff_or_ranked_choice_rule`

Senate 多数党目标必须由“留任席位 + 本届逐席模拟结果 + 党团归属 + 截止时点有效的副总统规则”计算，不得把 50 席或 51 席写成跨周期不变的硬编码。

### 2.3 预测时点

每个 horizon 独立训练、预测和评分。同一比赛在多个快照中重复出现，不会增加独立结果样本量。禁止随机切分 `race × snapshot` 行，也禁止把同一 `race/cycle/horizon` 的重复快照当成多次证据。

## 3. 结构解释与预测 nowcast 分轨

项目维护两个不能混淆的视图：

| 视图 | 允许信息 | 允许结论 |
|---|---|---|
| 结构解释 | 地图党派基线、总统党状态、事前经济条件、任职与空缺等战略反应前或明确建模的变量 | 描述稳定结构与条件关联；因果措辞仍需额外识别设计 |
| 预测 nowcast | 截止时点已公开的轮询、筹款、广告、评级、初选结果和候选人状态 | 提高当时预测，不把下游信号解释成原因 |

候选人质量、筹款、广告和专家评级通常受预期竞争性影响。它们即使通过预测基准，也只能进入 nowcast 轨道；没有独立识别策略时不得宣称因果效应。

## 4. 点时数据合同

### 4.1 三种时间

每个可变字段至少保存：

- `observed_for`：该数值描述的现实时期；
- `published_at`：来源首次公开该值的时间；
- `available_at`：本系统最早允许预测器使用该值的时间。

预测快照只能读取 `available_at <= forecast_as_of` 的版本。若时间精度仅到日期，默认按该日结束后才可用；不得把未知的日内发布时间提前到当天零时。

### 4.2 修订和来源元数据

需要修订追踪的字段必须同时具有：

- `source_id` 与原始来源名称；
- `source_version` 或内容哈希；
- `vintage_id`；
- `supersedes_vintage_id`，若该值是修订版；
- `retrieved_at`；
- `license_id`、许可名称、许可链接或本地许可文件引用；
- `allowed_use`，至少区分研究、再分发和商业使用；
- 派生特征的 `derived_from` 列表与变换版本。

没有许可信息不等于默认可用。下一轮真实数据接入时，许可状态未知的来源只能进入隔离区，不能进入训练面板。

### 4.3 地图时态

地图相关记录至少保存 `map_id`、`known_at` 和 `effective_from`。若 `known_at` 或 `effective_from` 晚于预测截点，该地图及其派生党派基线均不可用。当前地图上的历史总统结果若由选区级数据重新聚合，还必须证明组成数据在当时已经公开，并记录聚合算法版本。

### 4.4 结果隔离

`actual_*`、最终胜者、最终席位数和任何由最终结果直接派生的字段只能出现在结果存储区。预测器若请求这些字段，泄漏审计必须立即失败，不能仅发警告。

## 5. 泄漏登记表

以下任一情况使整次基准无效：

1. 使用测试周期的选举周期固定效应。
2. 用未来周期训练较早测试周期；这也是为何主验证不能采用 leave-one-cycle-out。
3. 经济变量使用最终修订值，而不是预测时点可知的 vintage。
4. 轮询按访谈结束日而不是公开可用时间截断。
5. 筹款按报告期末而不是申报公开时间截断。
6. 候选人质量、丑闻、退选、评级或党团归属使用事后编码。
7. 用实际胜负差定义竞争席位；竞争切片只能依据截点前基线。
8. 在全部周期上做标准化、插补、house effect 估计或超参数选择。
9. 同一比赛的不同快照跨训练折和测试折。
10. 用后来版本的地图、PVI、pollster rating 或特别选举结果回填过去。
11. 组件缺预测时删掉困难比赛；必须回退到直接父基线并按完整集合评分。
12. 在同一历史折上反复筛选大量组件后，仍把最终分数称为未见样本表现。

## 6. 有效样本量与切分

主验证采用按完整选举周期的扩展窗口滚动：

```text
训练：所有 cycle < t 且 office 相同的合法快照
测试：cycle = t 的完整 House 或完整 Senate 集合
推进：t → 下一届可评估周期
```

House 与 Senate 分别建折、分别评分。面向中期选举的全国参数还必须单独报告中期周期表现；把总统年与中期年混合后的总分不能替代这一结果。

必须同时报告：

- `n_rows`：参与评分的竞选行数；
- `n_races`：唯一竞选数；
- `n_cycles`：独立测试周期数；
- `n_midterm_cycles`：其中的中期周期数。

全国环境参数和多数党校准的主要有效样本量是 `n_cycles`，不是数千个地区行。逐周期先聚合竞选损失，再对周期等权；不允许人口较大的州、比赛较多的年份或多个快照制造伪精度。

历史 leave-one-cycle-out 可作为稳健性分析，但不得作为主时点回放，因为其训练集包含测试周期之后的信息。

## 7. 概率评分合同

### 7.1 竞选级

- 点预测误差：`MAE`、`RMSE`。
- 胜负概率：`Brier`。
- 连续预测分布：对数预测密度（越大越好）与边际 CRPS（越小越好）。前者不得与负对数损失混称。
- 区间诊断：50%、80%、95% 覆盖率及区间宽度。

连续对数分数要求模型提供合法的预测密度。评分器不得为避免无穷损失而静默裁剪零概率；非法、非有限或未归一化的预测必须失败。

### 7.2 议院级

- 席位点预测：席位绝对误差。
- 席位完整分布：离散 `CRPS`。
- 区间诊断：50%、80%、95% 席位区间覆盖率及宽度。
- 多数党概率：`Brier`。
- 席位—票数几何：每一点席位敏感度误差。

覆盖率不能单独决定晋级，因为无限宽区间也能获得高覆盖率。周期很少时，多数党校准和 95% 覆盖率只作诊断；概率组件的主依据是 proper score。

### 7.3 聚合与竞争席位切片

先在每个测试周期内等权平均竞选损失，再对周期等权。除全体比赛外，可报告一个由 `forecast_as_of` 前党派基线定义的竞争席位切片；禁止用实际结果定义切片。

## 8. 组件按职责晋级

组件不能使用一把统一尺子。`component-registry.json` 为每个组件预注册以下职责之一：

### 8.1 `required_benchmark`

M0 是永久实验对照，不需要击败其他模型，也不因表现差被删除。它的作用是固定尺子。

### 8.2 `race_mean`

改变竞选均值或边际胜率的组件必须：

1. 在相同扩展窗口折上改善至少一个预注册竞选级主指标；
2. 议院级守门指标不退化；
3. 保持完整预测覆盖，缺失时回退到直接父模型。

B1 属于此类。

### 8.3 `chamber_distribution`

相关误差和席位分布组件必须：

1. 改善至少一个议院级概率主指标；
2. 守住竞选边际指标；
3. 证明同一次抽样中共享全国误差，并另抽竞选误差。

这类组件不必改善竞选 MAE，因为它的职责不是移动单席均值。

### 8.4 `cross_layer`

声称同时改善竞选和议院层的组件必须在两层都改善。两院联合潜在环境、学习型集成和复杂 turnout 模块若提出跨层主张，适用此闸。

### 8.5 证据身份

| 身份 | 含义 |
|---|---|
| `required_benchmark` | 永久基准尺，不是现实有效性结论 |
| `synthetic_verified` | 仅证明合成夹具上的实现方向正确 |
| `queued` | 尚未满足依赖或缺少真实点时证据 |
| `historically_supported` | 通过真实历史扩展窗口滚动，但仍受回顾性调参限制 |
| `retained` | 满足预注册历史闸并经过版本锁定后的前瞻验证 |
| `rejected` | 硬闸失败或两轮有效试验无增益 |

在 `synthetic_only=true` 时，允许的最高身份是 `synthetic_verified`。本轮任何组件都不得成为 `historically_supported` 或 `retained`。

真实历史阶段的默认治理门槛是：`n_cycles < 8` 仅实验；8–11 届最高为暂留；至少 12 届才有资格获得历史支持。挑战者还应在至少 60% 的测试周期胜出、主损失相对改善至少 2%，并在按周期重抽样时达到 `P(平均损失改善) >= 0.90`；互补主指标退化不得超过 1%。这些阈值必须在看到对应测试结果前锁定。

上述 12 届全局门槛继续保留，但证据身份须按轨道声明可达上限。中期届 Senate 轨道只有 1986–2014 开发期与 2018/2022 评估期共 10 个独立周期，因此该轨道不可达全局 `historically_supported` 门槛，最高证据地位为 `provisional`；单个组件仍受自身预注册的更低上限约束，例如两周期评估只能到 `experimental_two_cycle_signal`。总统年 Senate 独立分轨仅登记为未来可选扩展；若开启，必须全新预注册，其证据不得与中期届 Senate 轨道合并。

若同一组历史折被反复用于选择组件，必须使用未参与选择的锁箱周期或多重比较校正。历史回测只能支持“历史有效”，不能替代真正前瞻检验。

## 9. 第 0 层组件

### 9.1 M0：当前地图党派基线

House 的 M0 使用预测时点有效地图上的党派基线；Senate 的 M0 使用州级党派基线。两者共享接口但不共享拟合参数和残差分布。M0 必须输出完整预测分布，而不仅是点预测。

### 9.2 B1：统一全国摆动

B1 在 M0 上加入同一院内共享的全国摆动。合成台架会故意生成共同冲击，因此 B1 应在该台架上优于 M0；这只是构造正确性的正对照。B1 本轮最高身份为 `synthetic_verified`。

### 9.3 相关席位模拟

每次抽样先抽一个该届共享的全国误差，再按规则抽州级或竞选级误差。不得把每场胜率当作 435 个或若干 Senate 比赛相互独立后相乘。固定种子下重复运行必须字节级一致；合成测试还须证明共享误差诱发正的同向协方差，并扩大席位分布尾部。

本轮 Senate 控制事件只由逐届**合成规则元数据**计算：当届竞选席、各党留任席、加入民主党团的独立议员、以及副总统党派共同决定控制阈值。它用于证明规则接口会对账并随周期变化，不是现实历史 Senate 规则数据库。真实轨道启用前，必须另行接入逐届可溯源的席位类别、特殊选举、决选/排序选择、党团和副总统元数据。

## 10. 后续组件队列

以下组件保持 `queued`，只有直接依赖通过真实历史点时验证后才可启动：

- 有尺度锚定的潜在全国环境和不规则时间步长状态空间模型；
- House 任职者、空缺席位和地图谱系；
- 候选人进入、质量、筹款和广告 nowcast；
- 按发布时间重建的竞选轮询观测模型；
- 独立验证后的 turnout 与议题激活组件；
- 低维、强收缩的地区异质弹性；
- Senate 候选人、第三党、决选和州轮询模型；
- 两院共享冲击与联合控制概率；
- 仅使用样本外预测训练权重的模型集成；
- 明确区分条件式与干预式含义的不确定性归因。

相关输入块下的 Shapley 归因取决于条件化定义和排列约定，不能直接解释成唯一因果贡献。首选可复核的 block ablation、冻结块敏感性和期望信息增益。

## 11. 下一轮真实数据进入标准

真实数据源只有同时满足以下条件才可进入候选区：

1. 有稳定的来源标识、版本或内容哈希。
2. 有记录级或可保守推导的 `available_at`。
3. 对会修订的数据保存原始 vintage，不用当前最终值覆盖历史。
4. 地图记录含 `map_id`、`known_at`、`effective_from` 和边界版本。
5. 候选人、轮询、筹款和评级含公开时间，而非仅事件归属日期。
6. 派生特征记录全部上游来源和变换版本。
7. 许可元数据明确，包括允许用途、再分发限制和署名要求。
8. 结果标签与预测特征物理隔离。
9. 能对 House 全部席位以及 Senate 本届全部常规和特殊选举进行覆盖审计。
10. 数据导入后先运行泄漏和对账报告，再允许任何模型评分。

若历史时点信息无法重建，必须标为 `not_point_in_time_reconstructable` 并排除对应 horizon；不得用最终快照填补。

## 12. 首轮停止条件

第 0 层完成只意味着：数据合同能拒绝已知泄漏，滚动折分无跨届污染，评分函数通过闭式测试，M0/B1 和相关模拟在合成正负对照上行为正确。它不意味着原提案中的政治机制已获支持。

任何高级组件若没有自己的中间目标、直接父基线和职责匹配的 proper score，应继续留在 `queued`。同一方向连续两轮在有效测试中无增益时，停止调参并重新拆解，而不是扩大模型。

## 16. 第 4 层：FEC 内容封印与解析权限边界（LH-057）

LH-057 只允许把 LH-056 已封印的三个最终 XLSX 对象作为本地研究快照取得。每个对象必须先做一次精确 HEAD，再做一次带 `If-Match` 与 `If-Unmodified-Since` 的条件 GET；正式网络面固定为 3 HEAD + 3 GET，拒绝其他 host/path/query、重定向、Range 和重试。HEAD 的 Content-Length、Content-Type、ETag、Last-Modified、X-Amz-Version-Id 必须逐字匹配前置封印；GET status、Content-Length、ETag、实收字节数和 8 MiB 上限必须通过。

落盘只允许同目录临时文件完成 fsync 后原子发布；半途截断、目标身份漂移或部分对象成功均只能生成确定性 `blocked_fec_content`，不能把临时文件视为快照，也不能同合同重试。`--write` 与 `--check` 不构造网络 transport，只读取本地 raw 文件和元数据日志。

内容检查的最深权限是 ZIP 目录遍历和 `xl/workbook.xml` 的 sheet 名称读取。明确禁止读取 `worksheets/*.xml`、`sharedStrings.xml`、任何单元格、票数、候选人或结果数值。因而 `content_sha256_verified=true` 只表示本地快照字节身份，`sheet_inventory_recorded=true` 只表示容器结构清单；行覆盖、结果完整性、许可复核、point-in-time vintage 和账本化必须另立接入合同。LH-057 不产生预测、评分、2026 概率或模型激活变化。

本轮监工唯一事务实际落为 `blocked_fec_content`：3 次 HEAD 全部通过，证明封印对象无漂移；3 次 GET 均因生产路径未创建 `data/raw/fec/` 失败，`FileNotFoundError` 又被宽异常处理掩蔽为 `GET_STREAM_FAILURE`。零结果字节落盘，根因是文件系统路径缺陷而非网络或来源；目录创建修复留给 LH-058。

## 13. 第 1 层：真实结果目标与 R0 哨兵

第 1 层使用 MIT Election Data and Science Lab `constituency-returns` 仓库的固定提交 `fe67c056502fc09ddb1ace2ff8f87c53233a744e`。清单同时锁定 URL、Git blob、字节数、SHA-256、DOI、CC0 许可、上游 House Clerk 来源和获取时间；离线核对不会把上游更新悄悄带入基准。

固定不等于合格。1976–2018 全部周期进入来源审计；2018 固定快照存在不同的 raw `totalvotes` 口径、unofficial 行，而且 DOI 已有更新版本。它继续留在原始目录和对账报告，但整周期 `benchmark_eligible=false`。raw `totalvotes` 不被改写；规范化总票数由候选人票逐行求和，差额另列。纽约跨主要党派 fusion、缺少党标和零票无人竞争仍保留唯一赢家，但连续两党边际为 null 并注明原因。

House `race_id` 含 cycle、州和当届 district，`district_is_cycle_local=true`、`map_id=null`。同号 district 跨届出现不构成地图谱系。Senate 本层没有留任席、席位类别、独立议员党团和副总统规则，所以只报告当届竞选席，禁止称为 100 席控制预测。

`R0_past_only_empirical` 是无特征哨兵，不是 M0。每折分院只读 `source_cycle < test_cycle` 的结果，先在训练周期内汇总，再对周期等权；预测阶段只能读取测试行的 `race_id/cycle/office`。改写测试届边际、赢家或实现全国摆动后，预测字节必须不变。

正式回测使用 1976–2016 合格周期、至少三个训练周期的 expanding-window rolling-origin，主切片为 `cycle % 4 == 2` 的中期届。1982–2014 共 9 个独立中期测试周期，因此最多是 `provisional`；R0 永久为 `required_benchmark/benchmark_only`。

第 0 层的 M0/B1 合成证据继续保留，但真实历史激活状态保持 `queued`。M0 需要预测时点有效地图或州口径的独立党派基线；B1 需要截至 `forecast_as_of` 冻结的全国环境预测量。`realized_national_swing` 是事后 outcome/diagnostic，注册为 `predictor_allowed=false`。任何 lineage 触及测试周期都必须失败，不能用实际摆动回退。

## 14. 第 2 层：Senate 州党派 M0 的档案重建

Senate 州界跨届稳定，因此先于 House 激活最小结构基线。对中期届 `t` 的州 `s`，M0 均值固定为该州 `t-2` 总统选举的民主党两党边际：`100*(D-R)/(D+R)`。主要党候选先按可验证姓名身份选出，再把同名 fusion 党线合并；不能按 `party` 字段直接求和。第三党、空姓名、Other、write-in 和 raw total 异常都留在来源账本。NE 2000 的两个 raw total 原样保留，特征分母只取已审计的 D/R 候选票。

M0 不拟合均值参数。每折只用严格更早的合格中期届，计算 `Senate margin − t-2 presidential baseline` 的零均值残差；先在每个周期内求 MSE，再对周期等权平均并开平方，尺度下限为 0.25。不得在同一组件里加入截距、斜率、州/时期效应、全国 offset 或概率校准；任何这些变化都必须另立预注册挑战组件。

总统机器可读文件是现代固定档案镜像，不是当年原始数据 vintage。特征账本把保守事实可知时间与镜像发布时间、检索时间分开，并声明 `historical_evidence_type=archival_reconstruction`、`strict_original_vintage_available=false`。本轮还条件于 LH-048 最终 Senate contest set；它没有证明更早预测时点已经知道所有 regular/special 竞选身份。

1978 没有残差训练届，1982 只有一届，因此正式配对测试固定为 1986–2014 八个中期届。M0 与 midterm-only R0 每折使用相同早期中期届、相同测试 race IDs 和相同指标分母。预注册闸要求：margin CRPS 相对改善至少 2%、至少 60% 周期胜出、固定种子周期块 bootstrap `P(mean delta<0) >= 0.90`，且 Brier 相对退化不超过 1%。实际四项均通过：CRPS 改善 11.7%、八届赢七届、bootstrap 0.9235、Brier 改善 13.7%。八届仍只够 `provisional`；M0 是永久 `required_benchmark/benchmark_only`，通过比较闸也不获得前瞻部署、2026 或 Senate 控制权许可。如果后续同口径竞速输给 R0，也只是否定当轮比较支持，不删除这把永久基准尺，更不得看分数后在同轮拟合 offset、slope 或校准救分。

当届竞选席 D 数分布只是假设竞选相互独立的职责外诊断。它不包含留任席、党团、副总统破平票或 100 席控制，因此不能称为 Senate 多数概率。House M0、B1、候选人、轮询、投票率、MRP 和跨院组件继续 `queued`。

## 15. 第 3 层：Senate 当届竞选席共享残差的探索性失败关闭

这一层只问一个狭窄问题：在父 M0 的每场均值、总边际方差和民主党胜率完全不变时，把残差中的一部分设为同一中期届共享，能否改善“当届已登记 Senate 竞选中民主党赢家数”的预测分布？它不是 B1：B1 需要预测截点前可观测的全国均值预测量；这里的共享项只是从严格过去中期届残差估出的零均值随机截距。它也不是 100 席控制模型，因为没有留任席、党团、席位类别或副总统规则。

每折先按训练届计算 `cycle_mean_residual`，再对这些届均残差的平方做周期等权平均。原始共享方差记为 `raw_shared_var`，实际使用 `min(raw_shared_var, parent_total_var)`，局部方差是父总方差减去使用后的共享方差；因此相关与独立版本的单席边际分布严格相同。若不固定这个恒等式，计数 CRPS 的变化会混入竞选层重校准，不能归因给相关结构。有效全国样本是训练周期数 `K=2..9`，不是每届三十多场竞选，更不是竞选对数；禁止 race bootstrap、同届拆分和未来周期 leave-one-cycle-out 主验证。

计数分布使用确定性一维正态分位混合。正式网格在首份 artifact 前因 8,192 点八折测试耗时 255.833 秒而冻结为 2,048；小型夹具证明 512、2,048、8,192 收敛，网格变更约 `5e-6`，不会改变任何闸。主分为离散 count CRPS，补充 log score 为 `log(PMF[actual_count])`，禁止 epsilon 裁剪；区间只作诊断。

八届结果中，相关分布 CRPS 为 3.7993，独立 Poisson-binomial 为 4.1127，相对改善 7.62%；相关版本赢五届，胜率 62.5%；固定 `seed=50071`、50,000 次周期块 bootstrap 的 `P(mean delta<0)=0.80642`，低于 0.90。三项职责闸因此未全部通过。更重要的是，全部八届在 LH-050 合同冻结前已经过只读方法探索，所以即便三闸意外全过也只能记探索信号、真实激活仍为 `queued`。当前正式状态为 `exploratory_not_supported`、`valid_nonpositive_run=1`；不得改网格、尺度公式、删周期或降门槛救分。只有未来新增锁箱周期或预先冻结的独立数据可以重新挑战。
## 16. Layer 4：在新周期接入前冻结 Senate 制衡方向先验

LH-052 把提案中的 balancing 拆成一个可证伪、职责很窄的组件，而不把它塞进仍缺点时全国环境源的 `B1_SENATE`。对开发周期 (s\in\{1986,1990,\ldots,2014\})，只使用该届 M0 的 out-of-fold 预测，先在届内计算连续边际残差均值 (r_s)。总统党符号固定为民主党 (z_s=+1)、共和党 (z_s=-1)，制衡幅度为

`b_hat = max(0, 0.5 * (mean_R(r_s) - mean_D(r_s)))`。

子模型逐竞选使用 `mu_child = mu_parent - z_t*b_hat`，父 SD 逐字复制，胜率由同一个 Normal 分布计算。周期先届内再等权；不拟合整体截距、斜率、党别独立系数、州效应、当届 offset 或概率校准。非负约束表达预注册的制衡方向：若开发窗方向相反，组件精确退化为 M0，不能在看结果后改名为 coattail 模型。

总统党按 `forecast_as_of` 时实际在任者从独立规则账本读取，不能从全国普选赢家推断。2000 年普选赢家与 2001 年就任者不一致，所以 2002 必须登记共和党；2016/2018 同理。账本的 fact availability 与现代引用版本分开，日期精度仍按日末后可用。

2018 与 2022 是一个共同 seal 下的 newly-added evaluation cycles：两届同时使用截止 2014 的同一参数，彼此不能进入训练。若解封后让 2022 使用 2018，只能另列 rolling sensitivity。主比较预注册为两届 Brier 都严格改善；当届已登记竞选的独立 Poisson-binomial 民主党赢家数 CRPS 只作护栏，不含留任席、党团或副总统破平票。独立周期只有 2，即便全部通过也至多是 `experimental_two_cycle_signal`，真实组件仍 queued，不得报告显著性或稳健性。

这里的 evaluation seal 不是盲锁箱：两届结果均已公开，旧 2018 快照也曾被完整性审计。它只证明公式、符号、截断、训练窗、指标、family 和 hash 规则在新版结果重新接入前被固定。真正 retained 仍需要版本锁定后的未来证据。

## 17. Layer 5：结果字节零接触的来源元数据封印

LH-053 先审计来源身份，再决定未来是否允许另立数据接入合同。可接受的官方 pin 必须同时确定数字 `MAJOR.MINOR` 版本、release time、dataset/file ID、唯一候选文件、filesize、checksum 类型和值、content type、restricted、许可、guestbook、固定 metadata URL、上传原件内容 URL 模板和覆盖范围；任一字段未知都必须失败关闭。

本轮正式 metadata 尝试数为 0，Senate 2022 与 President 2020 覆盖均未获得本轮官方核验。因而确定性结论是 `blocked_source_metadata`，而不是 `metadata_ready_for_separate_ingest_contract`。这是一次合格的失败关闭：系统在证据不足时保持 `result_byte_access_count=0`、`result_files_downloaded=0`，没有猜测版本、file ID 或 checksum，也没有以旧本地文件、搜索摘要或论文引用推断覆盖。既往 WAF 背景不能替代本轮正式获取证据；下轮只能在新合同中重试官方 metadata，或为官方 FEC 来源另立合同。

上传原件与 Dataverse 默认 archival 表示是不同对象。上传原件使用 `representation=original`，未来内容 URL 模板显式包含 `?format=original`；archival 表示可能发生格式转换，不能与上传原件混用 filename、checksum 或内容哈希。metadata 阶段只登记模板，绝不打开、读取或散列内容响应。guestbook ID 也只记录为未来访问前置条件，不在本轮提交个人信息或获取 signed URL。

```text
metadata seal（来源身份与许可）
  ≠ data seal（实际下载字节、大小与哈希）
  ≠ point-in-time vintage（预测截点时真实可得版本）
  ≠ 盲锁箱或前瞻验证
  ≠ 模型支持、晋级或部署许可
```

即使未来 metadata 完整，也只允许启动独立 ingest 合同；仍须在下载后验证内容身份、覆盖与竞选结果完整性。当前阻断状态不得填充 LH-052 的开发 OOF、评估父预测、contest inventory 或 predictions placeholder，也不得生成 Brier、CRPS、模型晋级结论或任何 2026 概率。

## 20. Layer 6.3：LH-058 内容封印修复与真实目录彩排

LH-058 延续 LH-057 的三份 FEC 最终 XLSX 冻结值，仅将合同号、metadata 目录和 artifact 名称隔离到 `LH-058`/`lh058`。技术门仍固定为逐对象 HEAD 后条件 GET、3 HEAD + 3 GET、8 MiB 单对象硬顶、完整字节数与容器身份封印；不读取单元格、票数、候选人或结果数值。

本轮修复了生产 raw 目录未预建导致的文件系统失败，并将捕获异常归类为固定 `FILESYSTEM_ERROR`、`HTTP_READ_ERROR` 或 `UNKNOWN_ERROR`。预检会写入并删除 canary；彩排会在真实生产目录跑完整 fetch 路径，校验合成 OOXML 后清理 raw、metadata 和 attempt 日志。监工随后完成唯一 3 HEAD + 3 GET，三个 XLSX 的本地快照内容身份与 sheet 清单已封印，`activation=fec_content_sealed`。语义边界保持严格：`data_ingested=false`，`row_coverage`、结果完整性、许可复核与 point-in-time vintage 均为 `PENDING_SEPARATE_INGEST_CONTRACT`；这不是结果完整性或正式接入证明。

## 18. Layer 6：FEC 官方传输对象身份封印（LH-054）

LH-054 只封印 FEC 官方 landing、href、编号 URL 的一跳 `302 Location` 和最终 XLSX 对象的 HEAD 身份。正式 allowlist 是四个 HTML GET 加六个 XLSX HEAD；禁止 PDF、附件 GET、Range、额外重定向、未知 host/path/query、userinfo、端口、fragment 和编码分隔符绕过。HEAD transport 用不读取正文的 canary 验证，正式账本必须保持 `formal_attachment_head_count=6`、`formal_result_body_bytes_read=0`。

三份对象的 Content-Length、MIME、opaque ETag、Last-Modified 和 `X-Amz-Version-Id` 必须逐字匹配预注册值。ETag 是 HTTP validator，不是 MD5、SHA 或内容哈希；Version-Id 只标识当前传输对象版本，Last-Modified 只表示对象修改时间。内容 SHA-256、ZIP/OOXML magic、sheet/schema、结果覆盖和票数守恒均固定为 `PENDING_SEPARATE_INGEST_CONTRACT`。

本轮 `--fetch-metadata-once` 只能消费一次事务，日志先于 transport，失败也不得同合同重试。无网络环境不构造假快照，而是保留失败日志并离线生成 `blocked_fec_object_metadata`。成功身份封印才允许下一份合同执行一次性条件 GET；它不是数据已接入、内容完整性证明、point-in-time vintage、盲锁箱、前瞻验证、模型支持、晋级或部署许可。FEC 公开下载也不等于显式许可或可再分发授权，登记为本地研究快照范围。

## 19. Layer 6.1：LH-056 第二次正式事务的职责拆分

LH-056 已由监工完成唯一一次正式事务，10/10 请求成功并得到 `fec_transport_object_metadata_sealed`。它仅参数化 LH-054 的传输对象封印实现，预冻结的 URL、href、Location、Content-Length、MIME、opaque ETag、Last-Modified 和 `X-Amz-Version-Id` 逐字复用，不重新猜测。`--contract-id LH-056` 将输出隔离到 `data/metadata/LH-056/` 与两个 `lh056` artifact；LH-054 目录、日志、artifact 由字节守卫保护。

一次性事务前必须先运行 `--preflight-only`。它检查 LH-054 已消费但 `activation=blocked_fec_object_metadata` 且 `formal_result_body_bytes_read=0`、LH-053 仍为 blocked、LH-052 `evaluation_access_count=0`、历史守卫未漂移以及 LH-056 输出目录为空，并证明 `attempt_created=false`。前置通过后，只有监工在中性域名出网预检之后执行一次 `--fetch-metadata-once`；Codex 只负责离线实现、文档、测试和回执收尾，禁止重试 fetch。

本轮报告必须同时保留 `prior_lh054_attempt_consumed=true`、`prior_lh054_real_fec_contact_count=0`、`supervisor_egress_preflight=neutral_host_only`、`precontract_public_search_result_snippet_exposure=true` 和 `secret_blind=false`。本轮成功只封印传输对象身份；内容 SHA-256、OOXML/schema、周期覆盖、许可与结果接入保持 `PENDING_SEPARATE_INGEST_CONTRACT`，不得写成数据已接入或前瞻证据。

## 21. LH-059：FEC Senate 结果账本与 LH-052 评估解封

LH-059 在本地消费已经由 LH-058 封印的三个 XLSX：先逐字节核对字节数与 SHA-256，再只读取 2018/2022 的 Senate 结果 sheet。解析器显式处理 sharedStrings、单元格类型、合并单元格和脚注；缺 sheet、合并歧义、非数字票数、重复州行和多赢家均确定性失败。2020 文件只参与封印验证，不把 House/President 数值写入 Senate 账本。

竞赛清单固定为 2018 年 33 regular + 2 special、2022 年 34 regular + 2 special。每届必须通过完整清单、race_id 唯一、赢家唯一、票数守恒和党派标签闸；任何一项失败都把该届标为 `benchmark_eligible=false`，评估入口失败闭合。M3 使用规范排序的完整 `race_id` 列表计算 SHA-256，并由 `senate_balancing` 和评估入口分别重算核对，拒绝缺项、额外项或 hash 不匹配。

FEC×MEDSL 2018 报告逐竞赛对账但不改写 MEDSL；MEDSL 仍为 `audit_only`。评估入口只接受截止 2014 的开发 OOF 和同一 cutoff 的 2018/2022 M0 父预测，禁止用 2018 训练 2022。主指标是两届严格 Brier，护栏是相同完整竞赛集合的独立 Poisson-binomial 计数 CRPS；报告分开 score/mechanism 两轨，禁止显著性、稳健性、historically_supported、2026 概率和 Senate 控制概率声明。当前本地缺少两个冻结父输入，入口已执行一次访问并锁定，生成失败闭合的 `preregistered_not_supported` 记录；不能用 2016 基线替代 2020 基线，也不能把缺源写成 Brier/CRPS 结果。

## 22. LH-060：封印后核验封印自身

[run-080](../../runs/run-080/log.md) 证明旧语义把 `historical_byte_guards` 指向的当前源码和 registry 当成历史封印的一部分：LH-059 合法修正 M3 与组件状态后，旧封印检查随即变红，使仓库演进与历史核验不可兼得。[run-081](../../runs/run-081/log.md) 因此把两个时点的职责分开：一次性事务创建前，`--preflight-only` 与 fetch 入口继续逐字核对活文件，保护网络预算和研究者自由度；事务完成后的 `--check` 只核验封印时刻事实与封印产物自身。

封印后核验的允许来源只有驱动内冻结的 artifact/config SHA-256、artifact 或封存 metadata 中记录的封印时刻快照，以及由 raw/metadata 等已封存输入进行的确定性重建。LH-052 预注册产物按冻结 JSON/Markdown SHA-256 和存量 JSON schema 核验，不再用当前代码重建历史字节；LH-053/054/056/057/058 同样不再追读旧策略所列活源码。封存 artifact、config、metadata 或 raw 任一真实字节变化仍会失败，因此这是核验对象的纠正，不是放松防篡改。

新语义可概括为：封印记录“某时刻哪些事实与字节成立”，不等于永久冻结整个仓库。当前源码、registry 或后续合同可以演进；历史结论只有在封印产物或封存输入被修改时才失效。

## 23. Layer 6.4：2024 总统结果对象的落地页动态锚定（LH-065）

FEC 2024 不再沿用 `federalelections20XX.xlsx` 合并工作簿命名，因此本层冻结落地页与 href 形状，而不冻结易随重传变化的 `documents` 编号。正式流程只有一次 landing GET 与一次动态对象 HEAD：保存原始 HTML 后必须先落 `extraction_started` 账，再从 anchor href 中取得唯一正则命中；相对或绝对 href 都归一化到同一 FEC HTTPS host。0 命中、多命中、归一化越界、HEAD 重定向或 header 契约失败均阻断，且不读取对象正文。

一次性预算由目录锚与 `state/lh-transaction-anchors.jsonl` 追加式外锚共同保护，任一锚存在都禁止重试；外锚先写，目录日志后写，任何 transport 必须在二者之后。冻结 policy/manifest 各自只读取一次，同一字节同时用于 SHA-256 校验和 JSON 解析。LH-053 的 `fetch_json_metadata` 也按 URL 策略段选择内容类型：metadata/guestbook 仍要求 JSON，说明页明确接受 HTML/XHTML，避免说明页 allowlist 与 JSON-only 响应实现冲突。

离线彩排用合成落地页覆盖相对成功、绝对成功、0 命中和多命中，并在真实 LH-065 metadata 路径执行创建、落账、提取、HEAD 审计和清理；socket/默认 transport 均不参与。当前只达到 `IMPLEMENTATION_READY`：未执行网络事务，未创建生产外锚、metadata 或 artifact，结果内容、州级覆盖、票数和 point-in-time vintage 均未获得新证据。

后续监工唯一事务的落地页与唯一 URL 提取成功，但对象 HEAD 坍缩为无细节的 `OBJECT_HEAD_FAILED`，最终封印为 `blocked_fec_object_metadata`；这说明失败账本至少应保留安全状态码，且多重强约束不应共用一个不可诊断的失败码。

## 23.1 Layer 6.4 重试：传输事实与内容策略分层（LH-066）

LH-066 不改动已由实弹证明有效的两跳设计：落地页 URL、href 正则、`https://www.fec.gov` 归一化基准以及先落 `extraction_started` 再唯一提取的逻辑均逐字继承 LH-065，生产路径仍不冻结 `documents` 编号。它只重构对象 HEAD 的事实记录：允许 200/301/302/303/307/308；200 至少具有正整数 `Content-Length` 与 `Last-Modified`，`Content-Type`、opaque `ETag` 和 `X-Amz-Version-Id` 有则记录；3xx 只要求 HTTPS `Location`，记录实际 host，不在传输封印层施加 FEC host 内容策略。

失败标识符固定为 `OBJECT_HEAD_STATUS_NOT_ALLOWED`、`OBJECT_HEAD_FINAL_URL_MISMATCH`、`OBJECT_HEAD_HEADER_CONTAINER_INVALID`、`OBJECT_HEAD_HEADER_VALUE_INVALID`、`OBJECT_HEAD_HEADER_DUPLICATE`、`OBJECT_HEAD_HEADER_MISSING`、`OBJECT_HEAD_LOCATION_INVALID`、`OBJECT_HEAD_CONTENT_LENGTH_INVALID`、`OBJECT_HEAD_TRANSPORT_ERROR`。每个约束只有一个独立失败码；诊断对象最多包含状态码、异常类名和约束名。响应正文、完整 header 集、异常消息和凭据不落账；Location 的 userinfo、query、fragment 会在记录前剥离，而 scheme 与 host 仍保留为可审计传输事实。

分层不等于放松安全：冻结落地页 allowlist、动态对象 URL 门禁、HTTPS、禁止附件 GET、HEAD 零正文、禁止重定向跟随与重试、一次性目录锚、追加式 state 外锚以及事务创建前可达性预检均保留。纯离线 preflight 不探测网络、不创建 attempt；彩排用合成 transport 覆盖 200、全部允许 3xx 与非法状态，并验证 301/307 Location 已记录。监工随后完成唯一事务并封印：对象 HEAD 为 302，HTTPS `Location` 有效，`Content-Length: 0` 记录的是重定向空响应体长度；`--write` 与 `--check` 均退出 0，终态为 `fec_transport_object_metadata_sealed`。这一封存事实确证 LH-065 将 302 响应体长度误作对象大小校验，正是旧 `OBJECT_HEAD_FAILED` 的根因；仍未读取结果附件正文，也未产生评分或预测。

## 23.2 Layer 6.5：2024 总统结果正文封印的实现闸（LH-067）

LH-067 把 LH-066 已封存的 `Location` 作为唯一内容对象身份。驱动每次加载配置时都从 LH-066 `http-heads.json` 程序化提取该字段，要求与 manifest 冻结值逐字一致，并单独执行 HTTPS、`www.fec.gov`、无 query/fragment/userinfo 门禁。生产驱动不含带编号的对象 URL。请求策略固定为一次直接 GET：前序 302 HEAD 的 `Content-Length: 0` 只是空重定向响应体事实，没有对象长度或 ETag 可供条件请求使用，重复 HEAD 不能增加有效身份约束。

正文在同目录临时文件中流式计数和哈希，超过 8 MiB 立即以 `CONTENT_SIZE_LIMIT_EXCEEDED` 关闭。流完成后只检查 ZIP magic、ZIP 目录、唯一 `xl/workbook.xml`、XML 可解析性及非空 sheet 名称清单；失败分别落为 `CONTENT_ZIP_MAGIC_INVALID`、`CONTENT_OOXML_INVALID` 或 `CONTENT_SHEET_INVENTORY_EMPTY`。HTTP 状态与文件系统分别使用 `HTTP_STATUS_INVALID`、`FILESYSTEM_ERROR`，异常诊断仅保留安全的状态码、异常类名、约束名。任何失败都清除临时文件且不发布目标；成功才原子替换，并在合同 access log 中记录字节数、SHA-256 与 sheet 清单。

四路离线彩排在真实 raw/metadata 目录走完整事务路径，覆盖成功、尺寸超限、magic 不符和 HTTP 失败；每场使用隔离外锚并在结束后恢复目录，不触碰既有 2018—2022 raw 封印。正式入口另受 `state/lh-transaction-anchors.jsonl` 追加式外锚保护；删除合同 metadata 目录也不能重新武装。纯离线 preflight 只做配置同源、前序哈希、目录/state 金丝雀和锚缺失检查，不发网络探针；正式入口必须在任何 attempt 或外锚创建前通过中性域名可达性检查。

监工随后亲执唯一事务 `bbccb260-c7f0-4f01-93a8-e2d7e43bbb40`，对封存 Location 单次直接 GET，`get_count=1`。正文原子落盘 21376 字节，SHA-256 为 `68acdee2924d771b92a05cd950dec850b462c633c05563207ac7e206116e7366`；ZIP magic、OOXML workbook 与单表清单 `["OFFICIAL 2024 PRES GE RESULTS"]` 全部通过，sealed `--write`/`--check` 均退出 0，activation 为 `fec_content_sealed`，业务终态为 `DONE_SEALED`。该体量符合单表州级总统结果专表的来源形态；2018—2022 多表合并工作簿约 0.6—6.2 MB，二者相差两个数量级不构成异常。

解析权限仍止于容器结构：不得打开 `xl/worksheets/*.xml`、`xl/sharedStrings.xml`，不得读取 cell、候选人、票数或结果数值。当前 `fec_content_sealed` 只证明本地字节身份和 sheet 容器清单，不证明覆盖率、结果完整性、许可或 point-in-time vintage，不激活模型、不评分、不产生概率。

### 基准层换轨（LH-062）

[run-083](../../runs/run-083/log.md) 将 LH-060 原则扩展到四个基准驱动与 LH-061 输入驱动。`benchmark.py`、`real_benchmark.py`、`senate_m0_benchmark.py`、`senate_joint_benchmark.py` 和 `build_lh061_inputs.py` 的 `--check` 不再调用当前 `build_report`、`build_outputs` 或渲染/重建路径，只核验驱动内冻结且经加载期格式断言的 SHA-256、存量产物记录以及 schema/证据边界；`--write` 仅保留为显式 vintage 生成夹具。

换轨没有放松核验：基础基准改用 `read_bytes()` 统一真实字节口径；真实目录副本测试证明五个驱动源码演进后十一项 check 仍绿，而每个新驱动所核验的 JSON、Markdown、JSONL 与审计 artifact 任一真实单字节翻转都会使对应 check 变红。既有 artifact、config 和 data 仍是签发时刻事实，一字节不改。

## 23. LH-063：审计遗留修复与精确枚举注册

时间字段从本轮起按角色解释。数据的 `available_at`、地图 `known_at/effective_from` 等仅日期值仍到次日 00:00 UTC 才算可用；`forecast_as_of` 的仅日期值固定为当日 00:00 UTC，不能借同一个“日末后可用”规则把预测截点向未来放宽。任何角色的无时区 datetime 一律拒绝，不按本机时区猜测，也不按善意方向补时区。

`models.py` 的 `pstdev` 数值行为保持不变。它是已冻结公式对周期总体矩与竞选局部总体矩的既定选择，不在审计修复合同中追溯更换。使用 `n−1` 自由度校正的样本标准差登记为未来挑战者；它必须另立预注册比较、只在训练窗拟合，并不得改写既有基准或封存结论。

“字节一致”只承诺同平台复验：同一 Python 实现与版本、操作系统、CPU 架构及其 `libm`。`math.erf/exp/log` 等超越函数在异平台最后若干位可能不同；跨平台只能先比较登记容差或规范化表示，不能把异平台位级差异直接解释为数据或模型篡改。既有封存产物仍按其创建平台的冻结字节核验。

模拟器新增 `per_race_substreams=true` 与逐竞选 `race_ids` 的显式选择性路径，以 SHA-256 从主种子派生稳定子流；增删一场竞选不会移动其余竞选的局部噪声。默认关闭时继续使用原单 RNG 调用次序，既有输出字节不变；该选择性 API 不自动改变任何正式基准。

精确周期块 bootstrap 登记为 **registered scale change**。公共入口 `exact_block_bootstrap_mean_distribution` 对 `n` 个周期抽 `n` 次，枚举 `C(2n−1,n)` 个多重集并保留各自在普通有放回 bootstrap 中的精确重数；八周期时恰为 `C(15,7)=6435` 个多重集、总有序权重 `8^8`。`exact_block_bootstrap_probability_below` 提供未来基准可调用的严格阈值概率。该变更消除 Monte Carlo 误差和 seed 依赖，但不重算、不追溯改判 M0、Senate joint 或任何已封存结论；首次用于正式比较须在新合同中显式启用并记录尺度变更。

## 24. LH-064：监督治理决议登记

本节仅登记 [监督治理决定书](supervision-governance-decisions.md) 的三项决议，执行记录见 [run-085](../../runs/run-085/log.md)。登记不改模型、评分、既有证据身份或全局 `may_emit_2026_probability`，也不生成任何预测数值。

第一，证据门槛改为“全局阈值保留、按轨道声明可达上限”。中期届 Senate 轨道最高为 `provisional`，组件级继续服从各自预注册上限；原至少 12 届才可获得 `historically_supported` 的全局阈值保留，并明确标为该轨道不可达。总统年 Senate 分轨只作未来可选扩展，开启须全新预注册，证据不得与中期届轨道合并。

第二，开设 `provisional_forecast_track`，并固定五条硬约束：任何产物必须携带 `provisional_forecast_track: true`、`forecast_as_of`、全部输入的 `available_at`，以及“系统设计上不可能在 2026-11-03 前完成前瞻验证，本分轨输出不是经验证的预测”的免责声明；分轨只可引用主体系组件及其如实证据地位，其产出不得增添组件证据、影响晋级或回流参数；只有通过自身预注册闸门的组件可进入组合，实际组合以 M0 结构核心起步；产物沿用 `supervision-tradeoff-note.md` 的分数轨/机制轨分栏；LH-063 的 M2 修复后泄漏闸照常适用。`SENATE_BALANCING_DIRECTION_PRIOR` 因 `fail_closed_evaluated` 禁止进入组合；若作对照展示，只能单独标注为“预注册评估未过闸的探索性叠加”。

同时登记 House chamber 分轨：它以全国两党票生成席位数分布，不逐席建模，状态为 `registered_pending_data`。启动前提是具有 `forecast_as_of` 与 `available_at` 的全国层 point-in-time 数据；它沿用 `chamber_distribution` 共用评分闸。登记只表示轨道可推进，不给任何组件授予新证据地位或预测许可。

第三，登记研究方向“制衡机制的条件化：何时失灵”。该方向只属于机制轨，只允许机制陈述与假设登记；2018/2022 结果已经公开，因此全部分析明确标注 post-hoc，不得包装成预测证据，也不得触碰已永久锁死的评分评估。可预注册的条件化假设只能等待 2026 实际结果之后作前瞻检验，或在总统年 Senate 分轨开启后于全新数据上预注册。

## 25. Layer 6.6：2024 总统结果解析与州基线扩展（LH-068）

LH-068 在 LH-067 已封存的 `2024presgeresults.xlsx` 上首次获得单元格解析权限。解析器按实际表头文字程序化定位列，读取 2—52 行的 50 州加 DC，并以第 53 行全国合计逐候选对账。资格闸要求 51 辖区、每州唯一最高票胜者、州内候选票守恒、所有非空票数单元格具有党籍类别、全国 Harris/Trump 与全候选合计同时守恒；另以冻结官方事实钉扎全国 D/R/总票及 AZ、GA、MI、NV、NC、PA、WI 七州胜者。其余候选若工作簿未给精确党籍，只标 `OTHER_OR_INDEPENDENT`，不离线臆造。

总统账本由 612 增至 663 行，新增段恰为 2024 的 51 行；Senate 州基线由 550 增至 600 行，新增段恰为 2026 的 50 州行，逐行记录 2024 来源、LH-067 内容封印与 LH-068 派生公式 lineage。两个既有前缀均以执行前行数和整段 SHA-256 护栏验证后，通过单次追加写调用发布，旧行逐字不动。

LH-061 的五项冻结语义只改变总统账本一项：签发时刻事实是前 612 行，检查对该前缀计算原冻结 SHA-256；后续合法追加不参与该项哈希。真实前缀字节翻转仍必红，663 行现状与额外合法后缀均保持绿。开发 OOF、评估父预测、总统审计与生成审计四项常量及整文件检查完全不变。历史 M0 与 joint 测试继续显式读取前 550 行冻结基线，新增 2026 派生行不进入旧评估；本层不评分、不生成预测。

## 26. LH-069：Provisional forecast track 的首个 M0 结构产物

[run-090](../../runs/run-090/log.md) 首次实际使用 LH-064 登记的 `provisional_forecast_track`。这不修改全局 `may_emit_2026_probability=false`：分轨数值的合法性只来自注册块的逐字免责声明、强制标注与单向隔离。产物不增加主体系证据、不影响晋级、不回流参数。组合恰含 `M0_SENATE` 结构核心；它的历史比较闸已通过，但组件证据仍只是 `provisional / benchmark_only`。失败闭合的制衡方向先验不进入组合，也不作探索性对照。

2026 目标身份只作结构推导。构建器从封存历史账本精确选择 2014 Senate regular 最终目标，得到 33 个唯一州，再映射为 2026 Class II regular 结构席。没有封存来源的特殊选举、候选人质量、全国环境和届中事件只进入 known-unknown 类别，不陈述具体时事。总统党结构上下文由封存 2024 总统账本 51 辖区的全国两党合计程序化派生为 `REP`；新配置记录账本 SHA-256，既有总统党中期账本保持零字节不动。该上下文不进入 M0 predictor，因为相应制衡组件已禁入。

`provisional_2026_vintage` 参数使用 1986—2014 八届开发历史与 2018/2022 两届 FEC 封存结果，共十届。现有州基线账本没有发布 2022 行，因此构建器只在内存中复现 LH-061 已验证的 2020 总统两党边际→2022 州基线公式，不追加账本；随后复用 `senate_m0.fit_senate_m0`，以十届周期等权残差 MSE 的均值平方根得到共享 `margin_sd=23.3956100054`。逐州 2026 均值仍逐字等于封存 2024 总统州两党边际，不拟合 offset、slope 或全国环境。

报告保持分数轨与机制轨分离。分数轨只引用冻结 M0 八届 OOF Brier `0.2180`、档案重建类型与 `provisional` 地位，并明确 2026 尚无事前分数；机制轨报告十届参数、M0 均值公式及共享尺度。逐席概率可汇总成独立 Bernoulli Poisson-binomial，但计数范围固定为 `structural_class_ii_regular_only`，不含留任席、特殊选举、党团或副总统规则，不构成参议院控制权概率。

全部八个直接输入逐项记录项目首次 `available_at`、证据回执、字节数与 SHA-256。`forecast_as_of` 为首次生成时的 tz-aware UTC 时刻；33 条结构快照全部通过 LH-063 M2 角色化时点语义的 `validate_snapshot`，晚到观测负例必红。2026 结果金丝雀保持 `blocked_before_open`、打开文件数为 0。五个新产物按 64 位小写 SHA-256 冻结；`--check` 不调用当前重建或渲染路径，真实单字节漂移必红。

## 27. LH-070：全国环境点时来源双源侦察设计

N 栈的全国环境输入分成两个不可混同的点时需求：A 要重建 2018/2022 在预测当时已经发布的 generic ballot 读数，B 要为 2026 持续取得带可追溯发布时间的最新读数。当前合同只做来源侦察，不接入数值、不评分、不预测，也不封印来源。候选枚举属于实现方知识，所有可达性、header、许可元数据和时间戳结构结论必须来自监工实测，两者在报告中物理分栏。

冻结计划覆盖 Wikipedia revision 历史、FiveThirtyEight GitHub 归档、VoteHub 聚合器 API 类和 RealClearPolling 备选四类，共八个 HTTPS 请求。Wikipedia API 只请求 revision id/timestamp，不请求页面内容；FiveThirtyEight 数据对象只 HEAD，许可 API 的 GET 不解码 `content`；其余候选只 HEAD 页面/API/条款入口。所有 GET 硬顶 256 KiB 且不保存正文，HEAD 的 `Content-Length` 只作为对象或响应传输事实，不能误当已读取正文大小。

一次性事务沿 LH-066 使用逐约束失败码、脱敏诊断、请求开始先落账、禁止重定向和重试，以及目录锚加追加式 state 外锚。正式网络可达性检查在创建事务前进行；失败则不创建任何锚。纯离线彩排覆盖成功、超限、状态不允和传输异常四路。探测完成前报告写入口确定性拒绝；完成后报告只从完整八请求账本重建“实现方知识 / 实测证据”双栏和 A/B 推荐矩阵，并按 LH-060 的封存输入确定性重建语义核验。

离线实现阶段终值为 `IMPLEMENTATION_READY`。随后监工亲执一次性事务 `5e400f0b-8aa6-4f1a-bfd6-d73f05eaf515`，8 请求约 4.6 秒完成且 `--write/--check` 均退出 0；全程零民调数值摄取、零正文持久化。业务终态转为 `DONE_PROBED`，仍不构成来源封印。

实测中只有 `538-license-api-get` 成功：GitHub API 确证 `fivethirtyeight/data` 的 SPDX 为 `CC-BY-4.0`，且未读取许可正文。五个 404 是源侧传输事实：Wikipedia 页面标题、538 raw 路径及 RCP 两条路径不可用；VoteHub API 根 404 只否定该根端点，不否定服务本身。另两项 `PROBE_HEADER_DUPLICATE`（Wikipedia revision API、VoteHub 条款页）属于我方侦察校验器缺陷：真实 CDN 的大小写异形或重复 header 被封印级唯一性约束误杀，不应归因于来源。

推荐矩阵初版如下：

| 渠道 | A：2018/2022 回测 vintage | B：2026 实时 | 下一步 |
|---|---|---|---|
| 538 GitHub 归档 | 首选；许可已证 | 不作为当前首选 | 验证内容路径、提交历史及当时可得性 |
| Wikipedia revision API | 次选，潜力仍在 | 可继续评估 | 分层修复侦察 header 校验后进行第二轮探测 |
| VoteHub | 暂缓 | 待定 | 取得具体 API/条款端点知识后再探 |
| RCP | 降级 | 降级 | 不沿用本轮失效路径，除非有新路径证据 |

LH-071 或后续合同仍须分别冻结数值内容、发布时间/版本 lineage 与许可边界；本轮实测只改变来源优先级，不授权摄取。

## 28. LH-071：侦察校验分层与 API 发现式两跳

LH-070 的实测把来源失败与我方校验失败分开：五个 404 是冻结候选路径失效的传输事实，而 Wikipedia revision API 与 VoteHub 条款响应因真实 CDN 重复或大小写异形 header 被拒，是封印级唯一性约束误用于侦察。LH-071 引用 LH-LESSON-246 修正职责：侦察层把允许 header 的全部值、原始名称、重复次数和大小写差异记录为事实；只有 HTTPS、状态、最终 URL、JSON 类型、合法长度与 256 KiB 正文硬顶仍是安全失败条件。历史 LH-070 artifact、metadata、配置和驱动保持字节不动，共用层通过 LH-070 形态夹具证明兼容。

路径知识不再扩散到目标对象。FiveThirtyEight 只冻结 `https://api.github.com/repos/fivethirtyeight/data/contents` 根锚；根目录 JSON 只读取 `name/type/url`，以冻结正则 `generic[_-]?ballot` 唯一选目录，第二跳 URL 必须逐字来自该响应并处于 GitHub contents API 前缀。目录清单只记录文件身份字段与 `download_url`，后者不进入 transport。由此可把 LH-070 已确证的 CC-BY-4.0 许可事实推进到文件级证据，但内容哈希、提交历史和实际 vintage 可得性仍待独立封印。

Wikipedia 只冻结 MediaWiki API 入口。第一跳 opensearch 只读取标题列表，候选须同时含 `generic` 与 `ballot` 词干，并以 `congress`、`poll` 词干对唯一最优项排序；无候选与最优并列分别使用 `DISCOVERY_ZERO_MATCHES`、`DISCOVERY_MULTIPLE_MATCHES`。第二跳由选中标题生成 query，只请求 `ids|timestamp` 的最新 revision 元数据，不请求内容、extract 或页面渲染。成功证据只支持 revision 级点时机制候选，不能替代许可与数值内容封印。

两条路线各最多两跳，冻结计划共 4 请求且低于合同上限 8；发现失败不执行第二跳。生产事务先追加外锚和目录锚，每个发现或详情请求都在 transport 前写 `request_started`，发现选择也在第二跳前落账。网络前置失败必须停在两个锚创建之前，目录锚或追加式 state 外锚任一存在都禁止重武装。离线彩排覆盖两路完整成功、0 命中、多命中、重复 header 记录和状态不允五类路径；解析器 AST/源码测试禁止民调数值字段和 CSV 路径，并用合成秘密字段证明未入证据。

离线实现阶段终值为 `IMPLEMENTATION_READY`。随后监工亲执唯一事务 `e1ad1b3f-1e97-41b4-96bd-0c2988c0bd83`，2 请求约 1.4 秒完成；零民调数值摄取、零响应正文持久化，`--write/--check` 均退出 0，业务终态转为 `DONE_PROBED`。

FiveThirtyEight 根发现跳唯一命中 `congress-generic-ballot`，其 API URL 为 `https://api.github.com/repos/fivethirtyeight/data/contents/congress-generic-ballot?ref=master`。该目录真名推翻旧知识路径 `generic_ballot_averages`，确证一轮 404 来自硬编码路径过时。详情跳在 transport 前被 `DISCOVERY_DYNAMIC_URL_INVALID` 拒绝：现有动态 URL 允许形态未覆盖 GitHub contents API 返回的规范 `?ref=master` 查询串。该失败码把发现成功与详情门禁失败精确分开；本轮账本可沿 LH-066→067 的模式充当后继合同冻结锚点，推荐 LH-072 先据此冻结动态 URL 身份，再直取目录文件清单。

Wikipedia opensearch 对 `generic congressional ballot` 返回 41 字节空集，`candidate_count=0`，因此未执行 revision 跳。下轮不再沿用前缀搜索，改用 `action=query&list=search` 全文搜索，并仅对唯一或最优命中取最新 revision id 与时间戳。重复 header 仍只作为事实记录，实测 `duplicates_are_facts_not_failures=true`，未产生误杀。

二轮实测后的推荐矩阵更新如下：

| 渠道 | A：2018/2022 回测 vintage | B：2026 实时 | 下一步 |
|---|---|---|---|
| 538 GitHub 归档 | 首选候选；许可已证，目录真名已发现 | 不作为当前实时首选 | LH-072 以本轮账本锚定含 `?ref=master` 的目录 API，直取文件清单 |
| Wikipedia revision API | 次选；当前尚无 revision 级证据 | 可继续评估 | 改用 `action=query&list=search` 全文搜索后再取 revision 元数据 |
| VoteHub | 暂时剔除 | 暂时剔除 | 取得可靠文档化端点后再入 |
| RCP | 降级剔除 | 降级剔除 | 除非取得新的可靠路径证据，否则不再消耗请求预算 |

本轮仍未下载数据文件、摄取民调数值、评分、预测或作来源封印；538 文件级清单与 Wikipedia revision 级证据均留待后继合同。

## 29. LH-072：环境源三轮收口侦察与终版矩阵生成器

三轮证据链分层如下。LH-070 的 `538-license-api-get` 实测确认 GitHub 归档许可 SPDX 为 `CC-BY-4.0`；LH-071 的 `538-root-discovery` 唯一发现 `congress-generic-ballot`，并把规范 API URL `https://api.github.com/repos/fivethirtyeight/data/contents/congress-generic-ballot?ref=master` 写入报告，但详情跳因旧门禁不允许 `?ref=master` 而未发出。LH-071 的 `wiki-title-discovery` 则证明 opensearch 前缀搜索为 0 命中。LH-072 不重解释这些历史事实：程序化读取 LH-071 artifact 并要求冻结 URL 逐字相等，538 改为单跳直取目录清单；Wikipedia 改用全文搜索后再取 revision 身份。

LH-072 的解析权限仍止于身份元数据。538 只记录文件 `name/size/sha/download_url/type`，不请求 download_url、不读取 CSV；Wikipedia 搜索只记录 `pageid/title/search_rank`，revision 只记录 `revid/timestamp/user_present`，不保留用户名、snippet、页面正文或民调数值。三次 GET 每次硬顶 256 KiB，重复 header 继续只记事实；正式事务仍由目录锚与 state 外锚共同防止重武装。

终版推荐矩阵由完整 LH-072 实测账本生成，离线实现阶段不伪造三轮结论：

| 需求 | 收口规则 | 具体实测证据 |
|---|---|---|
| A：2018/2022 回测 vintage | 若 `538-directory-inventory-direct` 清单唯一识别含 `average` 的历史均值文件，则首选 538，并把其 download URL、size、sha 交 LH-073 封印；否则明确声明选源缺口 | LH-070/`538-license-api-get`；LH-071/`538-root-discovery`；LH-072/`538-directory-inventory-direct` |
| B：2026 实时 | 若全文搜索与 revision 两跳成功，则 Wikipedia revision 历史为点时机制首选候选；正文、数值和许可仍待另立合同；否则明确声明实时来源缺口 | LH-071/`wiki-title-discovery`；LH-072/`wiki-fulltext-search`；LH-072/`wiki-latest-revision` |

LH-073 建议只在 538 唯一历史均值文件实测成功后进入 `READY_TO_SEAL_538_IDENTITY`：冻结该文件的 `download_url`、`size`、Git blob `sha`，许可依据固定引用 LH-070/`538-license-api-get` 的 `CC-BY-4.0`。Wikipedia 的 pageid、title、最新 revid、timestamp 和 user 字段存在性只登记为实时 revision 候选；本轮未证明页面内容再利用许可，因此不得借三轮侦察直接摄取正文或数值。

离线实现阶段终值为 `IMPLEMENTATION_READY`；随后监工亲执事务 `0d9b6cc3-035c-4e03-9054-191b2c4882b3`，2 请求约 1.6 秒完成，`--write/--check` 均退出 0，业务终态为 `DONE_PROBED`。全程未请求 download URL，未摄取 CSV 内容、页面正文或民调数值。

三轮实测最终收口如下：

| 需求 | 终版建议 | 实测证据与冻结参数 |
|---|---|---|
| A：2018/2022 回测 vintage | 首选 538 `generic_topline_historical.csv`；单一历史 topline CSV 覆盖回测 vintage 所需资源身份 | LH-070/`538-license-api-get`：`CC-BY-4.0`；LH-071/`538-root-discovery`：目录 API `https://api.github.com/repos/fivethirtyeight/data/contents/congress-generic-ballot?ref=master`；LH-072/`538-directory-inventory-direct`：size `754089`、Git blob sha `6a341f0ef020f9d8a46a45c5a2380d8215da866e`、download URL `https://raw.githubusercontent.com/fivethirtyeight/data/master/congress-generic-ballot/generic_topline_historical.csv` |
| B：2026 实时 | 声明来源缺口；独立 Generic congressional ballot 页不存在。候选容器 `2026 United States House of Representatives elections`（pageid `78311563`）仅供未来定向决策 | LH-071/`wiki-title-discovery`：前缀搜索空集；LH-072/`wiki-fulltext-search`：10 候选但页名选择器零命中，以 `DISCOVERY_ZERO_MATCHES` 失败关闭；未发 `wiki-latest-revision` 请求 |

因此建议 LH-073 封印 538 历史文件身份：冻结上述目录 API 锚、download URL、size、Git blob sha，并把许可依据固定为 LH-070/`538-license-api-get` 的 `CC-BY-4.0`。Wikipedia 候选容器不构成实时源选定、revision 身份或内容许可证明；其 pageid 只作为后续合同的定向入口。探测 artifact 的清单、请求事实和失败码保持原样，不以文档终版判断回写实测数据。

## 30. LH-073：环境源内容封印链

LH-073 把三轮侦察证据转换为可执行内容锚，但不把文档中的转述当作生产常量。新驱动 `lh073_environment_content_seal.py` 先按 manifest 冻结哈希读取 LH-072 JSON artifact，再以 `route_id=FIVETHIRTYEIGHT_DIRECTORY_INVENTORY`、`request_id=538-directory-inventory-direct` 和目标文件名唯一定位实测清单项，从中程序化取得 download URL、字节数和 Git blob SHA-1。许可同时要求 LH-072 的 `license_basis` 与 manifest 中 `CC-BY-4.0`、`LH-070/538-license-api-get` 逐字一致。因此，侦察报告负责来源身份，内容封印驱动负责把同一身份变成下载前硬闸，两层证据不靠实现者手抄接合。

选择新建专用驱动而不扩展 `fec_content_seal.py`，是因为本源是以 Git blob 身份锚定的 CSV，与 FEC 的动态 Location、ZIP/OOXML 容器和既有冻结常量无关；独立驱动也避免改动已经封存的历史 FEC 路径。正式路径只允许向 `raw.githubusercontent.com` 发一次 HTTPS GET，正文读取硬顶 1 MiB，禁止重定向、重试、Range 和凭据。可达性失败必须发生在事务锚创建前；一旦武装，state 外锚与事务内 access log 均先于 GET 落账，任一历史外锚都禁止重武装。

内容到达后依序执行独立硬闸：实际字节数与 LH-072 实测值相等；按 `SHA-1("blob <len>\\0" + content)` 重新计算 Git blob 身份；成功后记录封印 SHA-256。随后只将完整字节解码为 UTF-8，把首物理行交给 CSV reader 记录实际列名，其余行仅用 `splitlines()` 计数。实现不使用 `DictReader`、`QUOTE_NONNUMERIC` 或数值转换，也不保留任何数据行单元格。许可归属声明由 manifest 写入未来 JSON/Markdown 封印 artifact：数据来源为 FiveThirtyEight data repository，依 CC BY 4.0 使用。

离线实现先达到 `IMPLEMENTATION_READY`；`--rehearse-offline` 在真实 raw 根下的唯一临时子目录以合成响应覆盖成功、字节数不符、blob SHA-1 不符和 UTF-8 解码失败四路，结束后删除全部彩排目标。随后监工亲执事务 `63b301a3-92c4-4b5b-a7bb-292e27a189a0`：单次 GET 约 0.9 秒，754089 字节与 Git blob SHA-1 `6a341f0ef020f9d8a46a45c5a2380d8215da866e` 逐字命中 LH-072 锚点，封印 SHA-256 为 `b6d5b398b819e822e910a538974161bcec7e83c7785573ef406a35704e8962b9`；sealed `--write/--check` 均退出 0，业务终态转为 `DONE_SEALED`。

结构闸确认 UTF-8、总物理行 7670（含表头）、数据物理行 7669，表头为 `[subgroup, modeldate, dem_estimate, dem_hi, dem_lo, rep_estimate, rep_hi, rep_lo, timestamp]`。这只为 LH-074 提供 vintage 设计依据：`modeldate` 与 `timestamp` 需要在摄取合同中冻结 point-in-time 语义，`subgroup` 需要先冻结口径选择；本合同仍未解析任何数值单元格、评分或输出预测。

环境源封印链由 LH-070 的许可确证、LH-071 的目录发现、LH-072 的文件三元锚侦察和 LH-073 的内容双身份封印组成：许可、传输字节与 Git 对象身份分闸，四份合同共同把候选来源推进为可供后续摄取合同引用的本地封印输入。

## 31. LH-074：环境 vintage 账本化与覆盖守恒

LH-074 获准解析 LH-073 封印 CSV 的全部单元格，但没有口径选择权。摄取器将九列表头逐字一致、日期可解析、estimate 落在 `[0,100]`、hi≥estimate≥lo、`(subgroup, modeldate)` 唯一和总行数守恒拆成独立失败码。合法行不因数值表现被剔除；不合法行若存在，则在对账报告中按 CSV 行号保留原始字段和全部失败码。生产结果为 7669 行账本加 0 行剔除，恰好守恒于 raw 的 7669 数据行；来源实际只枚举出 `All polls` 一个 subgroup，全部入账。

账本字段固定为 schema 版本、`subgroup`、ISO `modeldate`、两党 estimate/hi/lo、UTC `available_at`、`available_at_basis`、时间解释选择和递归 lineage。lineage 含封印 raw 的相对路径、SHA-256 八位前缀、CSV 行号与原始 timestamp。`modeldate` 仅表示估计 as-of 日期；`available_at` 仅从发布 timestamp 得到。来源 7669 个 timestamp 全部是无时区英文格式，按最不利的最晚可用方向视为 UTC-12 本地时刻，再归一化到 UTC；显式 offset 和仅日期形态另有测试，后者沿 M2 available 角色在该日结束后才可用。

泄漏方向对账逐行验证 `available_at >= modeldate 当日 00:00 UTC`。若来源事实早于该界线，摄取器不修补、不剔除，只逐行记录后保留；实际 7669 行均不早于。对账报告同时记录 modeldate 全范围 1995-11-09 至 2016-11-06，以及 2018、2022 两次中期选举日前 180 天窗口。两个窗口实际都为 0 行，说明这份名为 historical 的 topline 文件并不覆盖合同希望诊断的两届窗口；覆盖不足依合同只是可行性事实，不改变入账结果，也不授权另选口径或来源。

`build_lh074_environment_vintage.py --write` 采用内容判定续传：已有字节与确定性重建相同则保持不动，漂移则拒绝覆盖。`--check` 不重建产物，只核验驱动内冻结的两项 64 位 SHA-256、行数/来源边界和逐行 UTC/lineage；真实账本或报告任一单字节翻转都失败。至此 LH-070 的许可、LH-071 的目录发现、LH-072 的文件身份、LH-073 的内容封印和 LH-074 的点时账本形成完整环境数据链；本层仍不评分、不加权、不平滑、不推荐口径。

## 32. LH-075：2018/2022 环境源四轮侦察实现闸

LH-074 确认既有 historical topline 的 `modeldate` 只覆盖 1995-11-09 至 2016-11-06，2018/2022 两个评估窗口均为零；同时全部 `available_at` 位于 2020-09，故其历史记录属于 `retrospective_reconstruction`，不能等同真点时证据。LH-075 只实现补源侦察，不读取任何新的民调数值。

路线一对 `https://api.github.com/repos/fivethirtyeight/data/contents` 单次 GET，完整保留根清单响应顺序，但每个条目只复制 `name/type`。`size`、`sha`、各种 URL、正文与未知字段全部丢弃。路线二对 `generic_ballot_averages.csv` 和 `generic_ballot_polls.csv` 两个历史出口各发单次 HEAD；只记录白名单响应头和状态分类，不访问响应正文。三次正式请求逐笔在 transport 前落 `request_started`，总预算 3、合同上限 6，禁止重试和跟随重定向。

推荐矩阵把实现方知识与实测证据严格分栏。projects.fivethirtyeight.com 候选的知识置信度为中等，并明确站点归档后的存续性未知；HEAD 只证明传输元数据，时点真实性仍为 `unknown_pending_content`。每个候选都记录 2018/2022 覆盖预期、等级依据，并引用 LH-074 的 `retrospective_reconstruction` 发现为分级基准。只有未来内容合同能把候选提升为 `true_point_in_time` 或确认其为回溯重建。若 GitHub 相关目录为空且两个 HEAD 都未确认可达，报告必须输出“新周期环境评估不可行、回退开发周期 OOF 方案”。

离线阶段只允许 `--preflight-only`、`--rehearse-offline` 与 `--check`。无网前置失败必须发生在一次性事务锚创建之前，探测前 `--write` 确定性拒绝；正式 `--probe-once` 只由监工执行。本阶段终值 `IMPLEMENTATION_READY`，不生成生产报告、不摄取 CSV、不评分、不预测、不封印来源。

## 33. LH-076：权衡首测

本轮把 [`supervision-tradeoff-note.md`](supervision-tradeoff-note.md) 提出的配对栈差值第一次落成离线测量。S 栈逐场保留冻结 M0 OOF 的预测边际与 `margin_sd`；N 栈只增加预注册全国环境直通项。1998、2002 只作训练折，2006、2010、2014 为三个等权评估届；每折的 `c` 只使用 held-out 之前全部届，以逐场 M0 残差对训练样本中心化的环境读数做无截距 OLS。

主指标三届等权 `Score(N)−Score(S)` 为 `-0.004192451965`，但 CRPS 护栏差为 `3070.675318260584`，超过零容差，故护栏未通过。异常大的护栏损失主要来自首折：1998 与 2002 的环境读数只相差约 `0.01006`，虽满足非零方差识别条件，却得到 `c=656.244364393153` 与约 `9262.11` 的 held-out 边际调整。后两折 `c` 分别约为 `1.24205`、`1.33791`；三折符号一致为正，但幅度显著不稳定。按预注册纪律，不因该结果回调参数、中心化方法或首折规则。

完整逐届 Brier/CRPS、环境读数、逐折 `c` 与双轨边界见 [`artifacts/lh076-environment-paired-benchmark.md`](../artifacts/lh076-environment-paired-benchmark.md)。证据级固定为 `development_cycles_retrospective_environment`：环境账本的 `available_at` 全在 2020-09，属于回溯重建而非真点时证据。分数轨只能说明本次配对损失，机制轨只能说明直通系数的符号与稳定性；两者互不背书，本测量不授权组件状态变化。

## 34. LH-077：权衡首测的协议迭代二

迭代二逐字继承 LH-076 v3 协议，唯一新增预注册识别地板：若训练折内环境读数极差 `max(E_train)−min(E_train) < 1.0` 个百分点，则该折 `c:=0`，N 栈退化为与 S 栈逐字相同；每折记录实际极差、冻结阈值与触发事实。阈值 1.0 是评分前常数，禁止按分数调整。实现直接导入 LH-076 驱动的输入读取、配对、泄漏硬闸、未触发折 OLS 和评分逻辑，LH-076 驱动及双产物保持原字节。

多重性铁律为：本迭代是对同一开发数据的第二次协议评估，迭代动因是识别病理（结构性）而非分数追逐，但多重性事实必须显式声明；LH-076 产物一字节不动、其结论永存；证据级仍为 `development_cycles_retrospective_environment`，无晋级授权。首测与迭代二均为有效测量，必须完整并列报告。

实际训练环境极差依次为 `0.010060000000`、`14.118530000000`、`20.624030000000`：只有 2006 折触发地板，三折 `c` 依次为 `0`、`1.242050713392`、`1.337911608868`。触发折的 N/S 规范栈字节哈希、Brier 和 CRPS 均严格相同。迭代二三届等权 `Score(N)−Score(S)=-0.013999643606`；CRPS 等权差为 `-0.650099105847`，按零容差护栏通过。该结果仅属于第二次开发数据协议评估，不改变证据级或组件状态。

## 35. LH-078：2018/2022 环境源五轮目录侦察

LH-078 只实现元数据侦察。驱动先以冻结 SHA-256 读取 LH-075 报告的 173 条根清单，再要求 manifest 中三个目标目录名逐字存在且类型为 `dir`；三个 GitHub API URL 均由同一 origin、contents 前缀、证据目录名与 `ref=master` 程序化拼接，生产代码不手抄资源路径。

正式路径按 manifest 顺序对三个目录各执行一次 GET，总请求上限 3、单响应硬顶 512 KiB、无重试和重定向。每个条目只投影 `name/type/size/download_url`，其中 `download_url` 只登记不进入 transport；未知字段、响应正文、民调数值与 CSV 解析结果均不持久化。每次 transport 前先写 `request_started`，目录锚与 state 外锚共同阻止重武装；环境重入哨兵和独占进程锁把同合同探测进程上限固定为一。

报告只用文件名扫描 `generic/ballot/national/topline` 词干并高亮候选。归档冻结的 2018/2022 预测输出目录只预估为 `near_point_in_time`：该等级仍须 LH-079 通过内容哈希、获取时刻与内部日期覆盖确认；普通 polls 容器保持 `unknown_pending_content`。若三目录无词干候选，报告如实给出空结论，并从 LH-075 根清单程序化列出未探测的相关剩余目录。离线实现终值为 `IMPLEMENTATION_READY`，不创建或消费网络事务、不评分、不预测、不封印内容。

## 36. LH-079：2018/2022 环境源六轮收口侦察

LH-079 以冻结 SHA-256 同时核验 LH-078 报告的 `polls` 矩阵行和同事务完整探测证据。报告行固定父目录、清单引用和五条计数；两个子目录名则逐字取自完整证据中的 `dir` 条目。URL 只由配置 origin、contents 前缀、父目录、证据子目录名及 `ref=master` 程序化拼接，不另写资源路径。

正式路径顺序执行两个子目录各一次 GET，总请求上限 2，单响应硬顶 512 KiB，无重试、无重定向。条目仍只投影 `name/type/size/download_url`；download URL 仅登记且永不请求。请求开始先落账，一次性目录锚、追加式外锚、环境重入哨兵和独占进程锁共同失败关闭。本轮不读取 CSV，不摄取民调数值，不评分或预测。

终版矩阵仅扫描文件名中的 `generic/ballot` 词干。`old_model` 作为 2018—2023 当年模型输出归档，清单级最高只预估为 `near_point_in_time`；`2024-averages` 对 2018/2022 保持 `unknown_pending_content`。若发现可下载文件，报告给出供 LH-080 使用的文件名、大小、download URL 和父清单 URL 锚；若无候选，则明确宣告仓库内未定位该序列，并只保留 Wayback Machine 侦察或放弃新周期环境评估、锁定开发届结论两项选择。离线实现终值为 `IMPLEMENTATION_READY`。

逐届两次测量的 S/N Brier、CRPS、差值和逐折 `c` 并排表，以及分数轨/机制轨边界，见 [`artifacts/lh077-environment-paired-benchmark-iter2.md`](../artifacts/lh077-environment-paired-benchmark-iter2.md)。

## 37. LH-080：六轮侦察至旧模型环境序列封印

补源链从 LH-074 暴露既有 historical topline 对 2018/2022 覆盖为零开始。LH-075 侦察仓库根与历史出口，LH-078 沿根目录证据进入三个候选容器，LH-079 再进入 `polls` 的两个子目录并以文件名词干定位 `old_model` 下的唯一 generic ballot 候选。LH-070 的许可探测已确认仓库为 `CC-BY-4.0`；LH-079 的冻结报告则提供文件名、download URL、字节数与 `near_point_in_time` 清单级判断。LH-080 不重新解释这些事实，只把它们转换为内容封印前的可执行硬闸。

生产锚由驱动按 manifest 中的 artifact 路径、SHA-256、建议状态、目录名和文件名定位键程序化提取；目标 download URL 与字节数不出现在生产驱动或新配置中。Git blob SHA-1 没有被 LH-079 清单持久化，不能手抄补入，因此正式事务分为两条顺序请求：第一条从 download URL 的仓库身份和相对路径推导 GitHub 单文件 contents API URL，只投影文件身份字段；只有 `name/path/download_url` 与 LH-079 锚一致、API size 与 LH-079 size 相等且 `sha` 是 40 位小写十六进制时，才把元数据锚先写入 access log。第二条正文 GET 的 URL 和 blob SHA-1 只取自该已落账元数据锚。元数据失败时事务以一条请求结束，绝不尝试正文下载。

正文层将传输字节、Git 对象身份和本地封印身份分为三个互不替代的闸：实际字节数必须同时命中 LH-079/API 尺寸；`SHA-1("blob <len>\\0" + content)` 必须命中第一请求的 blob sha；成功后另记 SHA-256。其后只做 UTF-8 解码、首物理行表头解析与总/数据物理行计数，任何数据行单元格都不进入 CSV reader，也不作数值转换。全部闸通过后才在 `data/raw/environment/generic_ballot_averages_old_model.csv` 原子发布。报告冻结时写入 FiveThirtyEight 归属声明、`CC-BY-4.0` 许可依据、三处字节数、两种哈希、表头与行数。

`--preflight-only` 与 `--check` 在干净状态只核验离线实现，不探测网络或建立事务。`--rehearse-offline` 在真实 raw 根下的临时子目录用合成响应覆盖成功、正文尺寸不符、blob sha 不符、解码失败以及 API size/LH-079 size 不符五路，完成后恢复目录。一次性入口在网络不可达时必须停在 state 外锚、access log 与进程锁之前；重入环境哨兵和独占锁把同合同进程上限固定为一。实现者不执行 `--fetch-content-once`，当前终值为 `IMPLEMENTATION_READY`，不摄取民调数值、不评分、不评估预测。

监工随后执行 LH-080 一次性事务 `35cc5904-5602-41b0-a26b-2a64bb3ee990`，第一请求即以 `PROBE_BODY_LIMIT_EXCEEDED` 关闭：GitHub 单文件 contents 端点为文件响应时会内嵌整份 base64 正文，229659 字节目标形成约 306 KiB JSON，超过轻量元数据上限。事务在正文下载前以 `CONTENT_BLOCKED` 完成，`request_count=1`、`retry_count=0`，零正文落盘。该失败说明单文件 contents 端点不能当作轻量元数据端点。

## 38. LH-081：目录清单取 SHA 的封印修正重试

`lh081_environment_content_seal3.py` 保留 LH-080 的两请求、双哈希、原子发布和一次性事务纪律，只把第一请求改为 LH-079 已冻结的 `polls/old_model` 父目录清单。目录 URL 由 LH-079 download URL 与仓库身份程序化构造，并与报告中的 `parent_listing_url` 逐字核对；响应上限为 512 KiB。目标条目只按 `name` 逐字定位，缺失或多匹配均失败关闭，持久化投影恰为 `name/type/size/sha/download_url` 五字段，Git blob SHA-1 只能来自该响应。

离线入口为 `--preflight-only`、`--rehearse-offline` 与 `--check`。彩排覆盖成功、目录条目缺失、目录 size 与 LH-079 不符、下载正文 blob SHA-1 不符和 UTF-8 解码失败五路，全部零网络、零生产锚。正式事务仍由监工执行 `--fetch-content-once`：目录 size 必须命中 LH-079 冻结字节数，下载字节数必须命中目录条目 size，本地 Git blob SHA-1 必须命中目录条目 sha，并另记 SHA-256。任何中间异常均收口为原子 `CONTENT_BLOCKED` 终态；重入哨兵和独占锁把同合同并发上限固定为一。本阶段不创建或消费一次性事务，不解析数值单元格、不评分、不预测，终值为 `IMPLEMENTATION_READY`。

监工随后完成两请求封印：9352 字节目录清单唯一定位到 size 229659、Git blob SHA-1 `571e05dae8ba0fe16f7eaee224a8e385f7cb2e4a` 的目标条目，raw 下载 229659 字节且本地 blob SHA-1 命中，封印 SHA-256 为 `caae521c49a1ec9387a84a1a40f8f5a4555215513334cb667474d4f2ff130840`；`--write/--check` 均退出 0，业务终态为 `DONE_SEALED`。结构闸记录表头 `candidate,pct_estimate,lo,hi,date,election,cycle`、总 3481 行和数据 3480 行，作为 LH-082 vintage 摄取设计依据，本层仍为零数值摄取。

## 39. LH-082：环境双账本的近点时补层

LH-082 获准解析 LH-081 封印 CSV 的全部单元格，但没有评分、口径推荐或平滑权限。摄取器将七列表头逐字、`date/election` 日期、有限数值、estimate 值域、hi/lo 次序、`(candidate,date,election,cycle)` 唯一键和总行数守恒拆成稳定硬闸。每个 raw 数据行对应一个 ledger 行；来源按两党候选分行给值，因此不在摄取层把两行合并。生产结果为 3480 行账本加零行剔除，恰与 raw 守恒；Democrats 与 Republicans 各 1740 行，三届合计六个候选/选举/周期口径全部入账。

来源没有发布或建模 timestamp，只有逐日 `date`。按合同的保守选择，驱动复用 M2 `_instant` 的 available 角色，把每行可用时刻设为模型日期次日 `00:00:00Z`；lineage 同时保留 raw 相对路径、完整 SHA-256、CSV 物理行号与七个原始字符串字段。泄漏方向检查逐行要求该可用时刻恰为次日零时且不早于模型日，实际 3480 行全部通过。

这份账本的证据等级是 `near_point_in_time`：2018—2023 序列在当年逐日生成，之后由 FiveThirtyEight 仓库归档冻结；但因缺少逐次发布时间戳，次日零时仍是保守近似。LH-074 账本则是 `retrospective_reconstruction`，其历史 modeldate 由 2020-09 的统一 timestamp 发布。对账报告把两种等级、依据与路径并列冻结，禁止把回溯重建和近点时归档写成同一证据强度。

日期全范围为 2017-04-15 至 2022-11-08。按同一 election 限定、排除选举日的前 180 天窗口，2018 与 2022 各覆盖 360 行，均为 Democrats/Republicans 各 180 行。这使下一合同可以评估新周期配对可行性，但本层不执行任何评分或模型判断。账本 schema 单列于 [`environment-oldmodel-vintage-schema.md`](environment-oldmodel-vintage-schema.md)；`--check` 以两份真实产物的冻结 SHA-256 做双向翻转回归，不从当前代码重建。

## 40. LH-083：权衡测量三部曲的新周期收口

权衡测量三部曲依次是开发届首测、协议迭代二和新周期测量。LH-076 首测在 1998/2002 训练后扩窗评估 2006/2010/2014，暴露首折环境极差过小却产生巨大系数的识别病理；LH-077 在评分前加入 `<1.0` 个百分点的识别地板，对同一开发数据完成第二次协议测量，并永久保留首测与多重性事实。LH-083 不再用开发折挑协议，而是在五个开发届 1998/2002/2006/2010/2014 上一次性终拟合，再首次把 B1 环境族送入 2018/2022 新周期评估。

终拟合沿 LH-077 的逐场、无截距、训练样本环境中心化 OLS。开发环境来自 LH-074 回溯重建账本；五届环境极差为 `20.624030000000`，未触发识别地板，165 场终拟合 `c=1.330783545486`、`mean_train(E)=0.677132121212`。机制轨把该终值与 LH-076/077 三个历史折的 `c` 并列，仅陈述符号和幅度，不为分数轨背书。

评估环境只从 LH-082 近点时账本程序化选取同届选举日当日或之前最近 `date`：2018 为 `2018-11-06`、`E_t=8.611540`，2022 为 `2022-11-08`、`E_t=-1.231613`。冻结 M0 父预测与既有 FEC 结果以 `race_id` 两侧全集逐字对齐；Brier 沿既有口径只纳入民主党或共和党胜者，CRPS 只纳入有限二党边际。两届等权 `Score(N)−Score(S)=-0.016372742330`；CRPS 等权差为 `-0.665125589342`，零容差护栏通过。分数轨只陈述本次 proper score，不为机制轨背书。

治理上，2018/2022 结果自 LH-059/061 起已公开；本合同是 B1 环境族的首次两届评估，与 LH-052 制衡族已锁评估相互独立，并显式声明跨组件多重性。训练环境为回溯重建级、评估环境为近点时级，综合证据级固定为 `new_cycle_mixed_vintage_environment`。本测量无晋级授权，不输出 2026 数值。

## 41. LH-084：B1 环境组件与民调同化方向注册

`component-registry.json` 将 `B1_SENATE` 的证据状态登记为 `experimental_mixed_vintage`。三部曲谱系逐字引用 `artifacts/lh076-environment-paired-benchmark.json`、`artifacts/lh077-environment-paired-benchmark-iter2.json` 与 `artifacts/lh083-environment-newcycle-evaluation.json`：LH-076 保留首测及 CRPS 护栏未过事实；LH-077 在同一开发数据第二次协议评估中登记识别地板，开发届 `Score(N)−Score(S)=−0.0140` 且 Brier/CRPS 双闸通过；LH-083 终拟合 `c=1.3308`，新周期 `Score(N)−Score(S)=−0.0164` 且双闸通过。两次开发协议评估的多重性永久记录。新周期只有 2018/2022 两届，因此本次仅登记证据，不授权晋级；晋级路径仍需更多前瞻周期。全局及组件 `may_emit_2026_probability` 均保持 `false`。

民调同化方向以监工签发的 `docs/supervision-poll-assimilation-note.md`（[权威原文](supervision-poll-assimilation-note.md)）为准，注册项 ID 为 `poll_assimilation_track`。形式化固定为 `state_space_inversion`：民调是潜在意见场的异质部分观测，v1 可用标准库 Kalman 滤波作全国一维反演；逐调解释账本只属于机制轨，按“模型场投影 + 抽样框效应 + 机构效应 + 时点效应 + 残差”的会计恒等式输出，不为分数背书，也不越界声称因果。

路线按原笔记分层：v1 需要含 `frame/mode/n/dates/pollster` 的民调级归档，注册后启动数据侦察；v2 需要州民调级归档，排队等待；v3 需要公开罕见的原始交叉表，数据缺口构成明确天花板。数据侦察沿六轮模式逐个收敛未知，不摄取数值，并分级记录点时真实性。参数只在开发届估计、逐折报告稳定性，并在新周期评估前预注册冻结。分数轨按 N₂ 民调同化栈对 N 环境直通栈进行 Brier 主指标、CRPS 护栏、识别地板和双轨分栏的配对测量。实时应用继续受 `provisional_forecast_track` 的既有五项硬约束与已知数据源缺口约束。

## 42. LH-085：民调级数据侦察离线实现

LH-085 从 LH-075 冻结报告的 173 条 GitHub 根清单中程序化确认 `pollster-ratings`、`early-senate-polls` 与 `august-senate-polls` 三个目录名。生产 URL 只由共同 origin、contents 前缀、证据目录名和 `?ref=master` 拼接；生产驱动不硬编码三个完整资源路径。三个目录各至多一次顺序 GET，总请求上限 3，单响应硬顶 512 KiB，无重试、无重定向。每个目录条目只投影 `name/type/size/download_url`；download URL 仅登记，绝不进入本合同 transport。

推荐矩阵只扫描文件名中的 `poll/raw` 词干。字段结构预估仅凭文件名与体量：`pollster-ratings` 的高体量命中可作为跨选举历史民调表候选，两个参院专题目录则只作为有限州场候选；`race/pollster/sample_size/start_date/end_date/poll_error` 等均明确标为待内容核验的预估字段，不是实测事实。v1 全国场对 ratings 类文件最多为条件候选，参院专题不是主要来源；v2 州场对两个参院专题为强候选、对 ratings 类为条件候选。目录清单无法证明历史可用时刻，三类候选的时点真实性统一预估为 `unknown_pending_content`。

若文件名命中，报告为下一份一次性内容封印合同建议冻结父清单 URL、文件名、size、download URL、内容 SHA-256、获取时刻、许可及内部字段/日期；若无命中，则封印锚如实为空。当前纯离线阶段只运行 `--preflight-only`、`--rehearse-offline` 和 `--check`，正式 `--probe-once` 与其后的 `--write` 仅供监工。重入环境哨兵和独占进程锁把同合同进程数上限固定为一。本合同不创建或消费网络窗口，不读取 CSV，不摄取民调数值，不评分、不预测，终值为 `IMPLEMENTATION_READY`。

## 43. LH-086：raw_polls 内容封印离线实现

LH-086 以薄配置画像复用 LH-081 的目录清单取 SHA 与下载双哈希逻辑，从冻结 LH-085 报告程序化取得 `raw_polls.csv` 的 URL 和字节锚，以 8 MiB 正文硬顶、三重完整性、UTF-8/表头/行数结构闸及零数值摄取边界停在 `IMPLEMENTATION_READY`，正式两请求事务由监工亲执。
