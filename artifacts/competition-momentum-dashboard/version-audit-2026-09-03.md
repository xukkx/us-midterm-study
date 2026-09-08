# 2026-09-03 仪表盘版本差异审计

## 结论

- 公开地址：`https://civic-race-signal-7k4m.pages.dev`。
- 线上 v6 的 `data.js`、`app.js`、`updates.js` 与本地主源 SHA-256 完全一致；线上并非落后版本。
- 当前冻结选举读数仍以 LH-169/LH-180 为准：底层截至 2026-08-31，原增量截至 2026-09-01。LH-216 另设 `latest-polls.js`，核验到 2026-09-03；它只叠加展示，不回写冻结账本、评级、模型参数或预注册动量。
- 后续研究改变的是不确定性说明：LH-178 判定当前 House 映射为未验证的跨院语境层；LH-179 的 `c=0.5` 影子挑战器在三个历史周期上更好但区间跨零；LH-181 的候选人/资源层历史上有增量但独立周期和统一点时不足；LH-182 的预注册 Senate 候选层失败，LH-183 的改善属于事后诊断。上述合同均未授权公开模型替换。

## 本轮公开层更新

1. 新增结构化 `model-review.js`，把后续冻结审计集中为一次全局说明，不改写 `data.js`、评级、预注册阈值或逐席点位。
2. House 的累计环境水平与四周动量继续分栏；卡片继续按现任党派着色并显示 `Flip possibility`。
3. Senate 折线继续显示逐份原始 D−R；逐卡只保留州级独有洞见。
4. 趋势图显示裁剪规则改为明示，并在每张受影响卡片列出所有边缘裁剪点的原始值、日期和机构。裁剪只影响图形纵轴，不删除或改写数据。
5. LH-216 新增 9 个州的 11 个参院正式对阵点，以及 TX-35 一项民主党阵营赞助的地区民调。每项记录访谈日期、发布日期、机构、样本口径、边际、来源与赞助状态。
6. 最新全国原始样本仍止于 8 月 31 日结束访谈的 Economist/YouGov（D+6）和 Reuters/Ipsos（D+5）；Silver Bulletin 9 月 2 日 D+6.6 只列作外部聚合快照，不替换冻结 E=D+6.2。

## LH-216 纳入与排除

- 纳入：Abacus Data 五州注册选民调查；Iowa Emerson；Texas Overton；Michigan EPIC-MRA；New Hampshire UNH；Minnesota SurveyUSA；New Mexico Research & Polling；TX-35 Normington Petts/HMP。
- 排除：Decision Desk HQ 的 9 月 1 日 TX/OH 数字（模型输出，无民调样本方法）；CO-08 Latino Policy Agenda（议题与观感调查，无正式候选人对阵）。
- Abacus 的 Maine 与 South Carolina 结果对 RV/LV 筛选高度敏感；趋势点采用每州明确 `n=500` 的注册选民口径，并在复核说明中披露 LV 子样本的方向差异。

## 线上 v6 基线证据

- `data.js`：`be459d985481269fcf108768302e49f0587d9f81df30d83ac5838d6a520e0ff1`
- `app.js`：`ca19fef8c8cd3ae9b89bd6ca7ac6145322d932cd9a8a490b35fb94d64b109493`
- `updates.js`：`a0d93c322409b587ea820803c9435e05e1b23bb6b00b3837ea6824e4c6afa21e`

本审计不修改任何冻结研究产物，也不构成模型晋级或 2026 概率预测。
