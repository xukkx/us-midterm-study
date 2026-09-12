"""冻结方案下的统计、效应尺度与预测结果；不把p值升级成机制。"""
import argparse,csv,io,json,math
from common import HERE,encode
LABEL={'conditional_legalization':'有条件合法化','drug_price_negotiation':'药价谈判','medicare_single_payer':'单一公共医保'}
def read(n):return json.loads((HERE/n).read_bytes())
def csvdata(rows):
 f=io.StringIO(newline='');w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows);return f.getvalue().encode()
def run():
 p=read('policy-calibration.json');h=read('history-nested.json');sim=read('simulation-results.json');v=read('verification.json');profile=read('lh266-profile-results.json');old=read('lh266-policy-results.json')
 lines=['# LH267：可观察限制校准与强度控制历史','','本轮保留LH266的结构结果，仅校准政策限制、增加一个嵌套历史预测器，并修复似然输入边界。有条件合法化政策对R1条件独立参考的偏离最明确：MI的Monte Carlo p=0.000040，六项Holm校正后0.000240。这个结论针对一个明确受限的观察模型，不排除所有静态类型或测量误差解释。','','控制2022年原八码党派认同后，2020年PID4历史仍增加折外预测信息：平均log分数改善0.008200 nats/人，相当于给真实观察答案的几何平均概率提高约0.823%。稳定与返回路径贡献为正，未返回变化路径为负；不是每类受访者都受益。','','## 1. 人群、回溯状态与预先固定的口径','','目标仍为同一6,175名三波保留受访者，政策各用自己的三波完整者。政策未知不变为反对或不变，未增加状态数或结果驱动子组。已看LH266、2024与评审探索置换结果；[本轮计划及封印](analysis-plan.json)只是新执行前规范，不是结果盲态注册。','', '| 政策 | 三波完整 | 任一未知（6175减完整） | PID返回且政策完整 |','|---|---:|---:|---:|']
 for item,d in p['items'].items():lines.append(f"| {LABEL[item]} | {d['R1']['complete_n']} | {6175-d['R1']['complete_n']} | {d['R2']['complete_return_n']} |")
 lines+=['','R1在基线PID4×政策20层内，保留完成PID路径的三组人数与2022/2024政策回答对的四类人数，均匀重分组；两年政策回答始终作为整体。每题99,999次。R2另外固定返回/稳定两组人数及总政策返回事件，作299,999次超几何抽样。它的零假设是**每层等概率**，统计量是绝对标准化平均差；不把它误写成仅要求平均为零的弱零假设。','','这两个条件参考要求层内记录可交换，并不是随机分配PID路径，也不使用全国调查设计。六个主检验为三题R1-MI和三题R2平均统计，统一Holm校正；TV是辅助统计，不用其更小p值另开显著性结论。另列三题家族校正只是与评审对照，不选较小校正作裁决。校正仅覆盖本轮指定六项，不覆盖项目的全部探索历史。','','## 2. R1：联合政策对的条件独立参考','', '| 政策 | 经验MI | 参考均值MI | 原始p（加一） | MC尾概率Wilson95% | 六项Holm |','|---|---:|---:|---:|---|---:|']
 table=[]
 for item,d in p['items'].items():
  r=d['R1']['statistics']['MI'];ci=r['MC_Wilson95'];lines.append(f"| {LABEL[item]} | {r['observed']:.8f} | {r['null']['mean']:.8f} | {r['p_plus_one']:.6f} | [{ci[0]:.6f}, {ci[1]:.6f}] | {r['Holm_primary_six']:.6f} |")
  for name,r in d['R1']['statistics'].items():table.append({'policy':item,'statistic':'R1_'+name,'observed':r['observed'],'null_mean':r['null']['mean'],'null_sd':r['null']['sd'],'hits':r['hits'],'B':r['B'],'p_plus_one':r['p_plus_one'],'MC_se':r['MC_se'],'MC_Wilson_lower':r['MC_Wilson95'][0],'MC_Wilson_upper':r['MC_Wilson95'][1],'Holm_primary_six':r.get('Holm_primary_six','辅助不裁决')})
 lines+=['','Monte Carlo区间量化有限随机抽样对条件尾概率的误差，不是政策效应区间。移民项的MI有3次抽样至少同样极端，TV为0次；仍用(hits+1)/(B+1)，不会给出零p值。完整零分布均值、标准差、分位数及尾计数见[机器可读结果](policy-calibration.json)。独立程序还用各格超几何分布精确求零参考MI/TV均值，三个项目的模拟均值均在相应Monte Carlo标准误的0.47倍以内。','', '| 政策 | 经验TV | 参考均值TV | 辅助原始p | 本轮TV解释尺度 |','|---|---:|---:|---:|---:|']
 for item,d in p['items'].items():
  r=d['R1']['statistics']['TV'];lines.append(f"| {LABEL[item]} | {r['observed']:.6f} | {r['null']['mean']:.6f} | {r['p_plus_one']:.6f} | {d['R1']['materiality_TV_scale']:.6f} |")
 lines+=['','有限样本下独立参考本身也有正MI/TV，因此没有把经验MI直接解释成机制强度。TV的解释尺度固定为该题原完整人群政策返回率的一半，用来讨论变化是否涉及基准返回模式的主要部分。三项经验TV均低于该约定尺度；**这不是等价检验**，本轮未给TV科学效应的置信区间，不能证明真实差异小到可忽略。该尺度没有外部测量研究的验证。','','## 3. R2：平均关联与逐层不等式分开','','原R2要求每层D_h≥0；正平均只是必要而非充分条件。新版本R2_eq_average_statistic_v1检验每层等概率，并用返回组的既定基线构成加权平均差汇总，不替换原R2。','', '| 政策 | 平均差（百分点） | 条件p | 六项Holm | 三项诊断Holm | 参考SD（百分点） |','|---|---:|---:|---:|---:|---:|']
 strata=[]
 for item,d in p['items'].items():
  r=d['R2'];lines.append(f"| {LABEL[item]} | {100*r['observed_average_difference']:+.3f} | {r['p_plus_one']:.6f} | {r['Holm_primary_six']:.6f} | {r['Holm_three_diagnostic']:.6f} | {100*r['null_distribution']['sd']:.3f} |")
  table.append({'policy':item,'statistic':'R2_eq_average','observed':r['observed_average_difference'],'null_mean':r['null_distribution']['mean'],'null_sd':r['null_distribution']['sd'],'hits':r['hits'],'B':r['B'],'p_plus_one':r['p_plus_one'],'MC_se':r['MC_se'],'MC_Wilson_lower':r['MC_Wilson95'][0],'MC_Wilson_upper':r['MC_Wilson95'][1],'Holm_primary_six':r['Holm_primary_six']})
  for z in r['strata']:strata.append({'policy':item,'PID20':z['baseline_PID'],'policy20':z['baseline_policy'],'return_n':z['return_n'],'return_events':z['return_events'],'stable_n':z['stable_n'],'stable_events':z['stable_events'],'difference':z['difference'],'simultaneous_lower':z['simultaneous_difference_interval'][0],'simultaneous_upper':z['simultaneous_difference_interval'][1]})
 lines+=['','三个平均差与LH266完全重现，新的独立随机数流也与评审探索结果在Monte Carlo误差内一致。医保项的三题诊断校正恰约0.05；主六项校正为0.07315，MC端点敏感性约[0.06947,0.07691]。不据小数四舍五入宣称发现；一次边界附近的p值也不认证逐层R2。','','为直接对照原逐层限制，另给18个有返回/稳定两组的层的同时保守区间：36个组内二项概率各分配0.05/36错误预算，先取Clopper–Pearson区间，再构造[L返回−U稳定, U返回−L稳定]。Bonferroni保证在另述的层×组独立Bernoulli参考下，整组至少95%覆盖；不要求各政策之间独立。这是不同于固定事件总数置换的抽样参考，仍不是全国调查区间。','', '| 政策 | 平均差同时保守区间（百分点） | 本轮实质尺度±ε（百分点） |','|---|---|---:|']
 for item,d in p['items'].items():
  r=d['R2'];ci=r['simultaneous_average_interval'];lines.append(f"| {LABEL[item]} | [{100*ci[0]:+.3f}, {100*ci[1]:+.3f}] | {100*r['materiality_epsilon']:.3f} |")
 lines+=['','所有18层的同时区间都跨零；这套保守区间既未证实所有层非负，也未检出某层上界小于零。基线“不确定”的两政策基线层每题没有PID返回者，明确不推断这些空组。医保两个基线I层的经验差仍为−4.389和−2.236百分点，正平均没有掩盖它们。完整原人数与层区间见[r2-strata.csv](r2-strata.csv)。','','ε为按返回组基线构成标准化的稳定组政策返回率的一半。理由是要影响该题基准返回模式的主要部分，而不是为所有题套同一百分点阈值；它是新计算前固定的操作尺度，尚无外部依据称其为已验证的科学最小效应。三项平均区间都远跨±ε，无法证明实质等价，也不能精确确定效应大小。保守性与返回组稀疏共同限制结论。','','## 4. 一个强度控制的历史挑战者','','母模型为P(PID24_4|PID22_8)，唯一新增项为P(PID24_4|PID22_8,PID20_4)，向母模型固定收缩20人。四类预测结局、6,175人、原哈希整人五折、缺失规则和母模型先验完全相同；没有调收缩网格。母模型分数与LH266复现一致。','', '| 模型 | 折外平均log分数（高为好） | 多类别Brier（低为好） |','|---|---:|---:|']
 for i,name in enumerate(['原八码母模型','原八码＋早期PID4']):lines.append(f"| {name} | {h['mean_logscore'][i]:.8f} | {h['multiclass_brier'][i]:.8f} |")
 lines+=['','五折的成对平均改善分别为'+', '.join(f"{x['paired_mean_difference']:+.6f}" for x in h['folds'])+' nats/人。它们使用重叠训练集，不是五次独立科学复制；本轮没有逐人重采样并完整重拟合，故不给算法层面的置信区间，也不把固定预测重采样冒充这种区间。','', '| PID4路径组 | 人数 | 组内平均log差 | 对全队列平均差的贡献 |','|---|---:|---:|---:|']
 for name,z in h['group_contributions'].items():lines.append(f"| {name} | {z['n']} | {z['paired_mean_difference']:+.6f} | {z['contribution_to_cohort_mean']:+.6f} |")
 lines+=['','137名返回者贡献明显为正，690名未返回变化者贡献为负；全64条字面PID4路径全部保留在[history-paths.csv](history-paths.csv)。这种分解揭示预测器的得失，不把返回路径重新包装成心理类型。','','四类分别用预先固定的10个等宽概率箱给预测均值、实测频率及人数，见[history-calibration.csv](history-calibration.csv)。D/I/R/不确定的ECE如下：','', '| 模型 | D | I | R | 不确定 |','|---|---:|---:|---:|---:|']
 for i,name in enumerate(['原八码母模型','加早期历史']):lines.append('| '+name+' | '+' | '.join(f'{x:.6f}' for x in h['classwise_ECE'][i])+' |')
 lines+=['','Brier改善，但D/I类的分箱ECE变大、R/不确定类变小。有限样本分箱ECE有抽样波动，未据此宣称全面校准改善。预测历史信息不识别心理机制，也不是未来选举预测。','','## 5. 结构结果冻结，两种拟合损失同时报','','维护验收实际重跑旧流程，但不新增模型、设置或拟合结论。定义δ*_K(τ)为固定LH265参考阈值下、两段潜变化都为零的模型所需测量漂移的下确界。旧见证只给δ*_3(2)≤0.10、δ*_3(10)≤0.075、δ*_4(10)≤0.15，没有匹配下界。','','K3、δ=0.10的零动态log L为−10303.761586：相对冻结LH265参考损失0.708682，相对同δ最佳达到模型损失8.657607。前者是原接受规则，后者为新增诊断；不重设原规则，不把任一种损失转成置信水平或后验赔率。全部16点的两种损失见[fit-loss-comparison.csv](fit-loss-comparison.csv)。','','## 6. 计算校准、维护与主张边界','','在新实证计算前固定5个模拟场景，每场400次，每次199个条件抽样。小表R1有2,520个标记分配、88个不同表，其非随机精确MI检验在0.05水平的实际拒绝率为0，说明这个小表的离散性很强；有限Monte Carlo检验仍可能偶尔越过阈值。不得把该场景的低功效外推成经验大表无能力。','', '| 检验场景 | 拒绝数/400 | 拒绝率 | MC Wilson95% |','|---|---:|---:|---|']
 for r in sim['scenarios']:lines.append(f"| {r['test']} / {r['scenario']} | {r['rejections']} | {r['rejection_rate']:.4f} | [{r['MC_Wilson95'][0]:.4f}, {r['MC_Wilson95'][1]:.4f}] |")
 lines+=['','R2小表的精确零参考拒绝率约0.01454；正向odds4备择较易检测，反向odds0.25场景未检出，均按原计划保留。没有为提高功效或获得更好故事追加场景。单元测试另检查零行、零列、稀疏边际、完整政策对、超几何穷举、CP覆盖、似然维度/零支持及嵌套预测回退。','','似然维护现拒绝非64格概率与正频数格的零支持，并去掉静默概率下限；正常生成的支持内结果仍须完整复现。原科学结果保持字节，只有LH266函数、维护说明及其封印/ZIP更新。原始版本仍由325ee0a提交固定。',f"独立核验{v['checks']}项通过，包括从匿名源重算分层人数、精确零均值/方差、多重校正、全部折外预测与校准；完整命令与分包信息见[README](README.md)。",'','[数学补充与主张层级](foundations.md)区分队列描述、可行性、条件统计、机制识别与因果识别。当前证据能挑战有条件合法化的特定R1，却没有把一般静态解释排除，也未解决未保留者的2024结果。下一步只有能限定测量关系或真实施测时点的证据才会缩小机制解释集合；不会再用更灵活的同源潜态拟合替代这些证据。','']
 fitrows=[]
 for model,d in profile['models'].items():
  for r in d['rows']:fitrows.append({'model':model,'delta':r['delta'],'zero_loglik':r['zero_change_best']['loglik'],'fixed_reference_loglik':d['fixed_reference_loglik'],'best_attained_same_delta_loglik':r['best_likelihood']['loglik'],'loss_vs_frozen':d['fixed_reference_loglik']-r['zero_change_best']['loglik'],'loss_vs_best_same_delta':r['best_likelihood']['loglik']-r['zero_change_best']['loglik'],'original_rule_unchanged':True})
 pathrows=[{**r,'PID4_path':'-'.join(map(str,r['PID4_path']))} for r in h['path_contributions']];calrows=[{'model':h['methods'][m],'PID4_class':j,**z} for m in range(2) for j in range(4) for z in h['calibration'][m][j]]
 claims=[{'level':'exact_cohort_description','claim':'三项原平均差及完整分母重现','limits':'保留人群和逐题完整响应目标'}, {'level':'feasibility','claim':'δ星的三个上界及两种拟合损失','limits':'旧见证、无新拟合、非真实误分率'}, {'level':'conditional_statistical','claim':'有条件合法化R1在固定层边际参考下不相容证据较强','limits':'可交换假设、六项家族、回溯指定、非所有静态解释'}, {'level':'conditional_statistical','claim':'R2同时区间不足以证实逐层非负或实质等价','limits':'稀疏、保守Bernoulli参考、空组不推断'}, {'level':'predictive_description','claim':'控制当前强度后早期PID仍改善平均log分数','limits':'改善不普遍，无算法CI或心理识别'}, {'level':'mechanistic_or_causal','claim':'未识别','limits':'缺乏独立测量锚、精确题目时点和干预设计'}]
 return {'report.md':'\n'.join(lines).encode(),'calibration-summary.csv':csvdata(table),'r2-strata.csv':csvdata(strata),'history-paths.csv':csvdata(pathrows),'history-calibration.csv':csvdata(calrows),'fit-loss-comparison.csv':csvdata(fitrows),'claims.json':encode(claims)}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args()
 for n,b in run().items():
  if a.check:assert (HERE/n).read_bytes()==b,n
  else:(HERE/n).write_bytes(b)
 print('报告与9校准/18层/64路径/80校准箱/16拟合损失表一致')
