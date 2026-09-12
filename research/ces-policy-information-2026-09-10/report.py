"""按冻结结果生成中文研究报告；--check逐字节核对。"""
import argparse,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(n):return json.loads((HERE/n).read_bytes())
def build():
    m,s=read('matched-test.json'),read('support-audit.json');mi,tv=m['statistics']['MI'],m['statistics']['TV']
    text=['# LH269：政策记录的信息与预测损失','',
      '保留 LH268 与历史模型。新检验提供了与预测信息集相匹配的条件关联证据；支持审计显示，总训练人数多仍可能缺乏实际目的地的训练样本。这些结果不构成新模型晋级或因果机制识别。','',
      '本轮目标为已进入三波发布的 6,175 人，包括 7 名早期政策记录未知者。2024 和此前结果已经查看，这是新指定的回顾性诊断，不是盲态预注册。不重新链接原始微观数据，不改变旧模型、折、收缩强度、政策题或检验家族。','',
      '## 与预测输入相同的唯一检验','',
      '`H=(PID20四类, PID22八码)`，`W=(policy20, policy22)` 整对保留，`Y=PID24四类`。检验 `Y ⟂ W | H`；W不包含policy24，H不包含完成后的路径。未知政策是可用记录类别，因此检验同时允许缺失模式含有信息。','',
      f'共有 {m["layer_n"]} 个非空条件层，其中 {sum(x["degenerate"] for x in m["layers"])} 个退化层；层人数范围 {min(x["n"] for x in m["layers"])}–{max(x["n"] for x in m["layers"])}。每层固定W与Y边际，均匀置换带标签个体；不是对可行列联表等概率抽样。主统计只有条件MI，TV是辅助统计。','',
      '| 统计量 | 观测值 | 解析零参考均值 | 模拟均值 | 命中/模拟次数 | 加一尾概率 |','|---|---:|---:|---:|---:|---:|']
    for name,x in [('MI（主）',mi),('TV（辅助）',tv)]:text.append(f'| {name} | {x["observed"]:.10f} | {x["analytic_null_mean"]:.10f} | {x["null"]["mean"]:.10f} | {x["hits"]}/{m["draws"]} | {x["p_plus_one"]:.5f} |')
    text += ['',f'固定种子为 {m["seed"]}。MI 与 TV 的尾部命中均为零，加一结果为 0.00001，不能写成 p=0。二项Wilson 95%区间均为 [0, {mi["MC_Wilson95"][1]:.8f}]；代入式MCSE为零不代表尾概率已被精确知道。MI/TV模拟均值分别距离解析均值 {mi["null"]["mean_minus_analytic_in_MCSE"]:.3f} 与 {tv["null"]["mean_minus_analytic_in_MCSE"]:.3f} 个均值MC标准误。这里的区间只描述模拟误差。','',
      '观测表在该条件可交换参考下很不寻常。它支持“早期可用政策记录与后期PID答案存在条件关联”，并不把经验MI当作真实条件互信息的无偏估计，也不保证这个固定收缩估计器能实现正预测增益。该检验与旧R1的结局、条件集不同，不能把p值大小排成证据强弱或嵌套检验。','',
      '## 现有挑战者的支持审计','',
      '读取冻结的五折training_cells和保存概率；按真实匿名联合格独立核对训练与留出计数。以下评分均只用留出人数加权，收缩系数 n_train/(n_train+20) 仅作描述。未再拟合，未调参。目的地贡献对未改变者定义为零，表中均值分母仍是该区间全部留出人。','',
      '| 支持轴 | 训练支持区间 | 留出人数 | 改变人数 | 平均收缩系数 | 完整log差/人 | 目的地log差总和 |','|---|---|---:|---:|---:|---:|---:|']
    for axis,label in [('totalcell_band','总单元'),('realized_targetcount_band','实际目标类别')]:
        for b,z in s['summaries'][axis].items():
            w='不适用' if z['weight_mean'] is None else f'{z["weight_mean"]:.4f}'
            mean='不适用' if not z['n_test'] else f'{z["loss_delta_mean"]["full_log"]:+.6f}'
            text.append(f'| {label} | {b} | {z["n_test"]} | {z["changed_n"]} | {w} | {mean} | {z["loss_delta_sum"]["dest_log"]:+.6f} |')
    zero=s['summaries']['realized_targetcount_band']['0-0'];neg=s['totals']['dest_log_negative_contribution']
    text += ['',f'总单元50+区间的目的地净差为 −21.210593 nats，比全队列净差 −17.760253 更负，因为其他区间有抵消收益。因此不能把损失概括成“只在总样本稀疏单元发生”。实际目标类别训练计数为0的 {zero["n_test"]} 人（其中改变 {zero["changed_n"]} 人）贡献 −45.708704 nats目的地损失，占所有负目的地贡献绝对值约 {abs(zero["dest_negative_sum"])/abs(neg)*100:.2f}%。这是描述性集中度，不是稀疏性因果效应。','',
      '实际目标类别计数使用了后来实现的类别，只能用于诊断，不能用于预测前路由。大量总训练样本和充足的特定目的地样本是两件事。更强合并是否有用仍未验证，本轮不据此网格搜索。','',
      '| 全队列评分（新−历史） | 均值差 |','|---|---:|']
    for k,v in s['totals']['loss_delta_mean'].items():text.append(f'| {k} | {v:+.10f} |')
    text += ['', 'log越高越好，Brier越低越好。完整log下降、两种Brier方向不同；继续保留历史模型。完整双轴表同时提供原始目标计数、概率均值、正负贡献和整数人数，见support-summary.csv及support-audit.json。','',
      '## 对LH268汇总的一项勘误','',
      '旧comparison.json的changed414挑战者汇总误包含了413名early_diff_keep者。正确集合为237名末期新改变者+137名返回者+40名第三类改变者，合计414。旧科学文件保持原字节，本轮添加可复算勘误；全队列主结论不受影响。','',
      '| 挑战者改变者总分 | 正确414人 | 旧误纳827人总分 |','|---|---:|---:|',
      '| full log | −1167.083013674 | −1287.537858324 |','| event log | −823.159634676 | −943.614479326 |','| destination log | −343.923378998 | −343.923378998 |','| binary Brier | 262.011567524 | 295.157131146 |','| multiclass Brier | 581.698027500 | 638.465453788 |','',
      '未改变者的目的地贡献恰为零，因此该列没变；其余列被污染。正确均值应以414为分母，不能把827人的总分除以414。','',
      '## 收口与复现边界','',
      '关联、真实律下的理想信息、估计器的实现表现保持分开。选择进入保留队列、答案测量漂移、未知政策的含义，以及如何估计稀有目的地概率仍未解决。此次结果不外推到失访者、全国选民或潜在心理机制。','',
      '下一次候选须使用未见标签的新评估，并按analysis-plan.json提前规定：完整log平均增益至少0.005 nats/人且单侧95%下界>0；两个Brier差的单侧95%上界均不超过0.001。阈值是前瞻治理选择，不是从当前数据估计出的实质门槛，也不反套LH268。没有新评估则不晋级。','',
      '本轮止于支持审计和这个单一匹配检验，不增加潜状态、政策题、路由规则或新预测器。完整重放用matched_test.py --reproduce；快速--check读取99,999份存档并重新计算所有表、摘要与尾部结果，明确不重新抽样。数学证明与通用评分背景见foundations.md，具体执行和分包限制见execution-provenance.json。','']
    return '\n'.join(text).encode('utf-8')
def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();target=HERE/'report.md';b=build()
    if a.check:
        if target.read_bytes()!=b:raise ValueError('报告与冻结结果不符')
    else:target.write_bytes(b)
    print('报告核验通过' if a.check else '报告已生成')
if __name__=='__main__':main()
