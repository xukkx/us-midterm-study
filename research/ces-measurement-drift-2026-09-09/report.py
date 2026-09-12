"""从冻结数值生成报告与审阅表，不重新选目标或阈值。"""
import argparse,csv,io,json
from collections import Counter
from common import HERE,encode,write
LABEL={'medicare_single_payer':'单一公共医保','drug_price_negotiation':'药价谈判','conditional_legalization':'有条件合法化'}
GROUP={'stable':'PID稳定','return':'PID返回','nonreturn_change':'PID未返回变化'}
def read(n):return json.loads((HERE/n).read_bytes())
def csv_bytes(rows):
 f=io.StringIO(newline='');w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows);return f.getvalue().encode('utf-8')
def run():
 p=read('profile-results.json');e=read('equivalence-results.json');h=read('history-results.json');pol=read('policy-results.json');v=read('verification.json');lines=['# LH266：多大测量漂移能够消除模型内的潜在变化？','','三状态主模型已找到两段潜变化均为零的概率模型：最大行总变差上限δ=0.10、相对冻结LH265参考的对数似然损失容差τ=2时可行；τ=10时，δ=0.075已有见证。这是本次有限搜索首先达到的网格点，不是已认证的最小漂移。δ不是答错概率，τ也不是置信水平。','','目标仍为三波发布且PID完整的6,175人。所有结果不加权；不外推未保留的两波人群、美国人口或地区选举。2024结果与评审数值此前已看过，本轮为新指定的回溯诊断，非盲态预注册。保留LH265，不增加状态数；K=3为主、K=4为敏感性。','','## 1. 精确观测等价路径','','路径保持各HMM的**拟合观察分布**，不声称精确拟合原始经验频数。共同跨时标签固定；最大漂移与按2022潜态质量加权的平均漂移分开。','', '| 模型 | 101点中合法点 | 静态终点最大TV | 逐态TV最大值 | 加权平均TV | 静态两段潜变化 |','|---|---:|---:|---|---:|---:|']
 for k,d in e['models'].items():
  z=d['rows'][-1];lines.append(f"| {k} | {d['feasible_n']} | {z['drift']['maximum']:.6f} | {', '.join(f'{x:.6f}' for x in z['drift']['per_state'])} | {z['drift']['weighted_average']:.6f} | 0 / 0 |")
 lines+=['','HMM3的101个网格点全合法；HMM4只有两个端点合法，99个内部点有负转移概率。失败原矩阵与最小值保留，未裁剪或当成合法估计。HMM4静态终点的稀少状态使最大漂移远高于加权平均，不能只报平均来淡化最差状态。逐点检查不等于整段连续路径认证。','','独立隐态穷举得到最大观察概率差 '+f"{v['maximum_equivalence_probability_error']:.3g}"+'；评审参考逐项检查713项通过。原HMM3静态等价终点需最大TV约0.1522；允许小幅拟合损失并重新拟合后，本轮找到了更低漂移的零动态见证。','','## 2. 两个容差轴下的有界搜索','','固定每个K原LH265的参考似然，所有δ共享它。每个上限使用冻结、多样与前一上限起点，保留合法等价见证；实际完成8个δ、两个K。每个δ/τ分别搜索g01、g12及其和的最小/最大端点；较宽集合继承较紧集合见证。','','| 模型 | δ上限 | 最佳达到log L | 零动态log L | 零动态相对参考损失 | τ=2找到零动态 | τ=10找到零动态 |','|---|---:|---:|---:|---:|---|---|']
 extrema=[];summary=[]
 for k,d in p['models'].items():
  for r in d['rows']:
   z=r['zero_change_best'];loss=d['fixed_reference_loglik']-z['loglik'];lines.append(f"| {k} | {r['delta']:.3f} | {r['best_likelihood']['loglik']:.6f} | {z['loglik']:.6f} | {loss:.6f} | {'是' if r['zero_change_fit_by_tau']['2.0'] else '未找到'} | {'是' if r['zero_change_fit_by_tau']['10.0'] else '未找到'} |")
   for x in r['extremes']:
    extrema.append({'model':k,'delta':r['delta'],'tau_loglik_loss':x['tau'],'objective':x['objective'],'attained_value':x['targets'][x['objective'].rsplit('_',1)[0]],'g01':x['targets']['g01'],'g12':x['targets']['g12'],'sum':x['targets']['sum'],'loglik':x['loglik'],'fixed_reference_loglik':d['fixed_reference_loglik'],'actual_maximum_drift':x['drift']['maximum'],'weighted_average_drift':x['drift']['weighted_average'],'minimum_middle_state_mass':min(x['diagnostics']['middle_mass']),'minimum_parameter':x['diagnostics']['minimum_probability'],'near_boundary_count':x['diagnostics']['near_boundary_count_1e8'],'status':x['status'],'global_certificate':False})
   for tau in [2.,10.]:
    ex={x['objective']:x for x in r['extremes'] if x['tau']==tau};summary.append({'model':k,'delta':r['delta'],'tau':tau,**{obj:ex[obj]['targets'][obj.rsplit('_',1)[0]] for obj in ['g01_min','g01_max','g12_min','g12_max','sum_min','sum_max']}})
 lines+=['','负“损失”表示比冻结参考拟合更好。HMM4在τ=10、δ=0.15已找到零动态；τ=2、δ≤0.20未找到，不代表不可能。端点集合、原参数、起点停止原因和所有搜索记录都在 [profile-results.json](profile-results.json)。','','[完整32行端点跨度表](attained-spans.csv)与[192个极值见证明细](attained-extremes.csv)同时公开。跨度只表示两个已达到端点；未证明两者之间每一点均可行，也不排除跨度之外仍有解。两段分别的最小值未必由同一模型达到，故另搜索g01+g12并保留参数。','']
 for k,d in p['models'].items():
  counts=Counter(x['stop'] for r in d['rows'] for x in r['likelihood_starts']);zc=Counter(x['stop'] for r in d['rows'] for x in r['zero_starts']);lines.append(f"- {k}一般拟合停止：{dict(counts)}；零动态拟合停止：{dict(zc)}。δ=0相对旧参考提升{d['source_same_emission_delta0_loglik_difference']:.8f}个log L单位。")
 lines+=['','δ=0的三套发射一致到1e-10，似然与原共同测量拟合相差小于本轮复核容差1e-3；并不要求重新优化后的参数逐位相同。独立检查原拟合概率最大差，HMM3为8.31e-7、HMM4为2.69e-7。所有192个极值见证的各发射/转移矩阵数值秩为K；数值满秩本身不证明良好条件数或实质测量分离。HMM3/HMM4极值见证的最小中间态质量分别约0.1371/0.00723，低于1e-8的边界参数最多分别12/24个。秩、质量与边界记录分开公开，不能用满秩掩盖稀少状态。']
 lines+=['','所有最优性证书均为false。small_gain只是相邻改进变小，no_ascent_proposal只是当前提议未找到上升；二者都不证明KKT或全局最优。极值搜索按固定次数停止。约束投影是可行提议，未称为精确约束M步。继承后的似然和端点嵌套检查均通过。','','## 3. PID路径与逐项政策回答','','PID稳定5,348人、返回137人、未返回变化690人，三组互斥且覆盖全体。按完成的三波PID路径分组是描述性筛选；不是基线处理分配。主表分母要求该政策三波完整；缺失不计为反对或不变。','', '| 政策 | PID路径 | 组人数 | 政策三波完整 | 任一未知 | 政策始终相同 | 政策返回 |','|---|---|---:|---:|---:|---:|---:|']
 policyrows=[]
 for name,d in pol['items'].items():
  for r in d['path_rows']:
   lines.append(f"| {LABEL[name]} | {GROUP[r['PID_path_group']]} | {r['retained_n']} | {r['policy_complete_n']} | {r['missing_any_n']} | {r['policy_stable_n']} | {r['policy_return_n']} |")
   for t,z in r['intervals'].items():policyrows.append({'policy':name,'PID_path':r['PID_path_group'],'interval':'2020-2022' if t=='0' else '2022-2024',**z})
 lines+=['','[逐段双向政策转换与完整/配对分母](policy-transitions.csv)保留18行。政策并非同一构念的可互换指标，未汇总成意识形态量表。','','在新联合表读取前另封印了两个窄限制（见[限制规范](policy-restrictions.json)）。R1要求给定基线PID和基线政策后，政策后两波联合分布与完成PID路径组条件独立；它比一般“标签噪声”解释更强。R2要求同一基线层内PID返回者的政策返回比例不低于PID稳定者；它只检验一种同步返回叙述。','', '| 政策 | R1经验条件MI（nats） | R1加权TV偏离 | R2按PID返回组基线构成标准化差（百分点） |','|---|---:|---:|---:|']
 for name,d in pol['items'].items():lines.append(f"| {LABEL[name]} | {d['restriction_1']['empirical_conditional_mutual_information_nats']:.6f} | {d['restriction_1']['weighted_empirical_TV_departure']:.6f} | {100*d['restriction_2']['standardized_difference']:+.3f} |")
 lines+=['','三项政策的R2方向不一致，不能支持一概同步返回的描述。R1的有限样本插件MI向上偏，不附显著性标签；两项限制均非一般潜态模型的必然推论，也不能藉此证明心理稳定或测量噪声。层内人数、对照覆盖与方向完整保留在policy-results.json。','','[施测时点审查](timing-audit.json)核对官方指南题干及变量、年度选前/选后范围，并证实每项每年在未参加选后问卷者中也有回答。这只能排除“选后独占”。profile的pid7不同于另列的选后CC*_pid7；本次未查得逐人题目时戳或同年PID与政策先后。因此本报告只谈年份记录，未声称同时测量、滞后效应或因果顺序。327d题干改变项继续排除。','','## 4. 观察历史基准与八码聚合','','使用原LH265的整人五折，同一6,175人、同一2024年PID4预测目标；训练时排除整个人的全部年份。PID4一阶先验总质量1、四类均匀；历史模型向该一阶分布收缩20人；原八码先验在每个PID4类别内部均分，聚合先验仍每类0.25。这些规则在本次对照计算前固定。','', '| 预测器 | 折外平均log分数（大为好） | 对PID4一阶改善（nats/人） |','|---|---:|---:|']
 for name,value in h['mean_logscore'].items():lines.append(f"| {name} | {value:.8f} | {value-h['mean_logscore']['first_order_PID4']:+.8f} |")
 lines+=['','历史和原八码预测器在五折均优于PID4一阶基准，但不据此作总体显著性或心理因果推断。八码强度信息解释了部分粗化预测损失；历史模型与原八码模型的复杂度和收缩形式仍不同。旧HMM分数使用不同正则化，只作为lh265-source.json中的背景，不混成公平排行榜。','','经验PID返回137人，对应观察一阶Markov拟合期望42.322987人，约3.237倍；条件MI为0.0214263 nats。2022年均为I的人中，2020年D的99人到2024年D/R为38/4，2020年R的132人到D/R为5/41。I只有原码4，不能单凭D/R强弱档聚合严格解释这一条件层的早期历史差异。有限经验差异不是总体一阶假设的正式拒绝。','','原八码2022→2024经验转移中，同一粗类各原码的下一粗类分布最大TV：D约0.05394，R约0.07145，I和不确定类因单码为0。这是强可聚合条件的经验诊断，未作总体检验；完整原码匿名表、训练计数、折外分数在[history-results.json](history-results.json)。','','## 5. 复核与本轮停止点','',f"独立核验{v['checks']:,}项通过，含{v['model_witnesses_checked']}个合法模型的隐态穷举、似然、漂移与目标。公开执行说明见[README](README.md)，识别集合与标签约定见[数学基础](foundations.md)。OpenCode Go Meta Muse 1.3实际交付了总变差内核，完整执行与独立验收摘要见execution-summary.json；研究计算和判断由监督端复核。",'','下一证据应优先给测量漂移提供可解释的锚或外部可靠性信息，并补齐题目时点；本轮不继续加状态、调收缩参数或寻找更有趣的子组。已有零动态见证使“必须存在潜在政治变化”的跨模型结论不成立；仍不能把δ容差解释为已知真实误差率。','']
 claims=[{'claim':'零动态可达到','scope':'三波留存6175人、K3、δ=.10、τ=2','status':'attained_feasible_witness','not_claimed':'最小所需漂移、真误分率、人口零变化'}, {'claim':'精确等价路径','scope':'LH265拟合观察分布；HMM3的101网格点、HMM4两个端点','status':'verified_grid_witnesses','not_claimed':'HMM4内部合法或整段连续认证'}, {'claim':'有界目标跨度','scope':'每个K、δ、固定参考τ下192个达到端点','status':'local_search_without_global_certificate','not_claimed':'锐界、全区间可行、95%置信区间'}, {'claim':'政策返回不统一','scope':'三项分别定义的完整响应群体；两项窄描述限制','status':'descriptive_observed_restrictions','not_claimed':'一般测量噪声反证、因果效应或通用意识形态因子'}, {'claim':'历史信息改善预测','scope':'固定整人五折、同一PID4目标与6175人','status':'out_of_fold_descriptive_comparison','not_claimed':'潜心理机制识别或人口显著性'}, {'claim':'时点范围有限核定','scope':'官方指南与未参加选后者回答计数','status':'exact_item_timing_unresolved','not_claimed':'同年题目先后、同时性、滞后因果解释'}]
 return {'report.md':'\n'.join(lines).encode(),'attained-extremes.csv':csv_bytes(extrema),'attained-spans.csv':csv_bytes(summary),'policy-transitions.csv':csv_bytes(policyrows),'claims.json':encode(claims)}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args()
 for name,b in run().items():
  if a.check:assert (HERE/name).read_bytes()==b,name
  else:(HERE/name).write_bytes(b)
 print('报告、32行跨度、192个端点、18行政策转换及主张记录一致')
