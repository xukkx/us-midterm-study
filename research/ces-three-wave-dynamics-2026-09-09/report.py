"""从已封存数值生成中文报告与可审计主张记录。"""
import argparse,json
from common import HERE,write,encode
def load(n):return json.loads((HERE/n).read_bytes())
def pc(x):return f'{100*x:.4f}'
def generate():
 r=load('results.json');d=load('trajectories.json');b=load('measurement-results.json');s=load('recovery-results.json');ex=load('exact-results.json');inv=load('indicator-inventory.json')
 names={'observed_markov':'观察四态Markov','hmm3':'共同测量HMM3','hmm4':'共同测量HMM4','static3':'静态类型3／时变测量','static4':'静态类型4／时变测量'}
 order=['observed_markov','hmm3','static3','hmm4','static4']
 lines=['# LH265：三波动态能与测量改变区分吗？','',
 '实际三波拟合支持一个有限结论：共同测量的三态和四态HMM都给出较高持续性、较低潜在总变化；但静态类型配合时变测量可以完全复制各HMM的观察分布。留出回答评分也无法确定演化心理机制。这个跨模型限制是本轮结果的一部分。','',
 '本轮已看2024，是回溯研究。主目标为三波发布保留者的字面PID轨迹，未加权整数人数；不外推美国人口或原两波全部人群。旧LH262—264和原件保持字节不变。完整假设、证明与计算边界见[识别基础](foundations.md)，计划见[analysis-plan.json](analysis-plan.json)。','',
 '## 人群与观察轨迹','',
 '|2020固定组|两波文件人数|三波保留|三波PID完整|至少一次不确定|真正缺失|','|---|---:|---:|---:|---:|---:|']
 for g,v in d['denominators'].items():lines.append('|'+g+'|'+'|'.join(str(v[k]) for k in ['two_wave','retained','complete','not_sure_any','missing_pid_any'])+'|')
 lines+=['','两波caseid与三波caseid_20连接；唯一键、七基线字段、caseid_22与pid7_22均核对。PID7=1—3→D，4→I，5—7→R，8→不确定。所有6,175人均有三波PID；另有4,834人没有进入三波发布。子组只作描述，不拟合稀疏潜模型。','',
 '|人群|2020→22回答总变化%|2022→24回答总变化%|返回原回答%|R回答净变化20→22 pp|R回答净变化22→24 pp|','|---|---:|---:|---:|---:|---:|']
 for g,v in r['observed'].items():lines.append('|'+g+'|'+'|'.join(pc(v[k]) for k in ['gross01','gross12','return','R_net01','R_net12'])+'|')
 lines+=['','返回指Y20=Y24且Y20≠Y22。全部64条轨迹及预测人数见[trajectory-comparison.csv](trajectory-comparison.csv)，包括零格；[trajectories.json](trajectories.json)提供完整匿名三组频数和整人五折充分统计，不含连接键或逐人资料。','',
 '## 两波测量假设敏感性','',f'本段目标另为完整两波11,009人：字面回答总变化{pc(b["identity_measurement"]["latent_gross"])}%，R净变化{pc(b["identity_measurement"]["latent_R_net"])}个百分点。单位测量解释与零潜变化、自由后波测量解释同样复现该表；后者最大误差{b["zero_latent_change"]["max_reconstruction_error"]:.2g}。共同独立测量且零潜变化要求对称；经验表最大不对称{b["asymmetry_max"]:.6g}，只是精确经验限制的失败。','',
 '|每波错误概率上限（假设）|潜总变化外界%|潜R净变化外界pp|','|---|---:|---:|']
 for row in b['budget_rows']:lines.append(f'|{pc(row["per_wave_budget"])}%|'+ '—'.join(pc(x) for x in row['gross'])+'|'+'—'.join(pc(x) for x in row['R_net'])+'|')
 lines+=['','每波仅0.5%的预算已经使R净方向的保守外界跨零；总变化下界仍为正。预算不是估计错误率，外界不是锐界或置信区间，也不是三潜态HMM的参数区间。','',
 '## 模型在观察尺度的比较','',
 '|模型|训练log L|观察轨迹TV距离|预测首段总变化%|预测次段总变化%|预测返回%|留出末波条件log分数|留出三波joint log分数|','|---|---:|---:|---:|---:|---:|---:|---:|']
 for name in order:
  f=r['fits'][name];q=f['observed_summary'];cv=r['cv_summary'][name]
  lines.append(f'|{names[name]}|{f["loglik"]:.4f}|{f["observed_TV"]:.6f}|{pc(q["gross01"])}|{pc(q["gross12"])}|{pc(q["return"])}|{cv["last_wave_conditional_log_score"]:.6f}|{cv["joint_log_score"]:.6f}|')
 lines+=['','分数为每人的平均自然对数概率，越大越好；同一人的三个回答始终在同一折。静态模型未强制测量不变，因此训练似然不低于相应HMM；两类模型的留出分数相近，不能把微小分差解释为心理机制证据。观察Markov仅条件于上一回答，对返回路径的预测偏低，提示回答过程的记忆比简单观察Markov丰富；稳定个体差异也可以产生该现象。','',
 '## 潜尺度结果与模型内部诊断','',
 '|模型|潜总变化20→22%|潜总变化22→24%|潜返回%|E/T01/T12数值秩|E Gram条件数|最佳起点收敛/迭代|','|---|---:|---:|---:|---|---:|---|']
 for name in ['hmm3','hmm4']:
  f=r['fits'][name];q=f['latent'];lines.append(f'|{names[name]}|{pc(q["gross01"])}|{pc(q["gross12"])}|{pc(q["return"])}|'+ '/'.join(str(f['rank'][k]) for k in ['E','T01','T12'])+f'|{f["gram_condition_inf"]:.3f}|{f["converged"]}/{f["iterations"]}|')
 lines+=['','持续性为1减去各段潜总变化。以上是共同测量、指定状态数、保留人群条件下的拟合值，没有人口区间。三态与四态变化率不同；静态时变测量见证的类型变化恒为零，观察分布仍相同。因此跨这两类测量机制，潜变化为正并非已识别结论。','',
 '独立检查中，HMM4有4个发射/转移参数低于1e-8，最小初始潜质量约1.02%、中间质量约0.97%；三态没有此类近零参数。满秩与稀疏边界可以同时存在，不采用常规内部点卡方近似。完整数值见[verification.json](verification.json)。','',
 '|拟合|12起点log L范围|收敛起点数|','|---|---:|---:|']
 for name in ['hmm3','static3','hmm4','static4']:
  starts=r['fits'][name]['starts'];lines.append(f'|{names[name]}|{min(x["loglik"] for x in starts):.5f} 至 {max(x["loglik"] for x in starts):.5f}|{sum(x["converged"] for x in starts)}/12|')
 lines+=['','随机起点都围绕对角占优的发射和转移初始化；这里没有观察到明显不同似然模式，但该搜索覆盖有限，不能证明不存在其他模式。数值秩阈值1e-9；满秩不证明测量稳定性，也不检验模型真实性。','',
 '共同发射E如下。Z编号只是算法标签，置换不改变潜总变化。','']
 for name in ['hmm3','hmm4']:
  lines += [f'### {names[name]}发射概率','','|状态|D|I|R|不确定|','|---|---:|---:|---:|---:|']
  for i,row in enumerate(r['fits'][name]['model']['E']):lines.append('|Z'+str(i+1)+'|'+'|'.join(f'{x:.5f}' for x in row)+'|')
 lines+=['','HMM3的首段潜总变化约束轮廓在预定网格5%附近最好。零首段变化相对未约束拟合的2倍log L损失为'+f'{r["profile"][0]["twice_loglik_loss"]:.3f}'+ '；这是该共同测量HMM内部的描述性拟合差，不能当作排除静态时变测量模型的证据。[profile.csv](profile.csv)保留全部网格、收敛与约束误差。没有套用卡方阈值或声称95%区间。','',
 '## 先于实证的计算检验','',
 f'精确观测tensor恢复共50例（K3/K4各25）；最大参数误差{ex["maximum_parameter_error"]:.3g}，静态映射最大误差{ex["maximum_static_error"]:.3g}。恢复不读取真参数，仅在最后按标签置换比较；秩退化例被明确拒绝。','',
 '|K|测量|n|重复数|最佳拟合收敛比例|首段潜变化偏差pp|RMSE pp|偏差MCSE pp|T最大误差中位数|','|---|---|---:|---:|---:|---:|---:|---:|---:|']
 for x in s['summary']:lines.append(f'|{x["k"]}|{x["quality"]}|{x["n"]}|12|{x["convergence_fraction"]:.2f}|{pc(x["gross01_bias"])}|{pc(x["gross01_RMSE"])}|{pc(x["gross01_bias_MCSE"])}|{x["median_T_max_error"]:.4f}|')
 lines+=['','96个模拟数据集使用两种人数、两种状态数和两种测量强度。强测量对角概率0.95、弱测量0.58；T01对角0.92、T12对角0.88，四态初始第四类稀少。弱测量所有最佳拟合都在300次迭代上限前未满足停止准则，已全部纳入误差汇总；误差混合了有限样本、局部最优与计算未收敛，不能仅归因于不识别。每格仅12次，MCSE估计粗略；收敛比例0或1时插件MCSE为0不等于概率已知。模拟结果不验证真实CES测量假设。','',
 '## 可扩展指标与下一条识别证据','',
 '|指标|三波二元回答完整人数|当前状态|','|---|---:|---|']
 for x in inv['items']:lines.append(f'|{x["wording"]}|{x["complete_binary_n"] if x["complete_binary_n"] is not None else "不适用"}|'+('题干不一致，排除' if not x['comparable_years'] else '候选；测量锚与局部独立未验证')+'|')
 lines+=['','[指标清单](indicator-inventory.json)逐项保存三个年份字段、题干、类别频数、缺失和来源。公共医保、药价、移民立场是不同实质问题，尚不能视为独立反映同一潜特质。PID7和其四分类派生不是独立测量。精确题块时点限制见清单；本轮没有扩大多指标拟合。','',
 '下一步最能区分现有等价解释的是有外部理由相信稳定的测量锚或同一时点的独立复测，并检验新增指标局部依赖。更多同类模型或更小的条件标准误不能自行消除动态与测量漂移的等价。','',
 '## 复现与执行','',
 '标准库Python 3.12。先运行experiments.py，再运行analyze.py；所有拟合、五折和轮廓都能仅凭匿名64格重跑。原件连接与政策缺失审计需要本地官方CSV；公开包不含逐人资料。代码完整复现与包校验命令见[README](README.md)。','',
 'OpenCode Go Meta Muse 1.3实际交付前向概率内核；完整输入、模型身份、正常结束、工具0及独立K³穷举均核验。一次启动，已报费用0.0005089美元。其余谱恢复、EM、模拟、实证和验收由监督者完成。','',
 '公开CI配置包含本轮检查，但账户启动限制尚未解除时，配置与本地通过不能算远端CI通过。最终提交及最新CI状态以PR回执为准。','']
 claims=[]
 def claim(id,source,population,target,assumptions,identification,estimation,uncertainty,wording):claims.append(dict(id=id,source=source,population=population,target=target,assumptions=assumptions,identification=identification,estimation=estimation,uncertainty=uncertainty,allowed_wording=wording))
 claim('observed_trajectories','trajectories.json','三波保留且PID完整6175','字面回答改变','编码与连接正确','经验队列点描述','整数轨迹频数','不含总体抽样推断','回答改变，不称潜心理变化或人口效应')
 claim('two_wave_zero_change','measurement-results.json','两波11009','潜总变化','自由时间/状态测量','非点识别，至少两个见证','精确矩阵构造','无统计区间','零潜变化与字面变化解释均兼容')
 claim('budget_bounds','measurement-results.json','两波11009','有共同标签的潜变化与R净变化','每波错误概率预算','保守外界，未证明锐性','并集上界','预算是假设，非估计误差和CI','给定预算下的外界')
 claim('hmm_parameters','results.json、exact-results.json','三波保留6175','模型内潜总变化','共同E、Markov、满秩、正质量、K3/4','理想法则下标签外唯一；真实拟合不证明假设','多起点EM近似MLE','轮廓是描述，模拟含未收敛；无人群CI','条件于模型的潜变化估计')
 claim('cross_model_equivalence','results.json/static_equivalence_witness','HMM诱导观察分布','静态还是演化机制','允许静态U与时变测量','跨模型不识别','每个HMM的静态映射','代数等价非抽样误差','拟合不能证明心理状态演化')
 claim('retrospective_prediction','results.json/cv','同一保留队列整人五折','观察响应概率','训练/测试按整人分组','观察分布表现，不识别潜真值','joint及末波条件log评分','训练重叠；无独立折显著性检验','模型回答预测表现接近，不认定真实机制')
 return '\n'.join(lines),claims
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();text,claims=generate()
 if a.check:assert (HERE/'report.md').read_bytes()==text.encode();assert (HERE/'claims.json').read_bytes()==encode(claims)
 else:(HERE/'report.md').write_bytes(text.encode());write(HERE/'claims.json',claims)
 print('报告和6条主张记录核验通过' if a.check else '报告和6条主张记录已生成')
