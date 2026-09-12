"""由封印的匿名结果生成中文报告及紧凑审阅表。"""
import argparse,csv,io,json
from common import *
G={'all':'全体','Latino_employed_2020':'2020拉美裔在业','R_renter_2020':'2020共和党倾向租房'}
M={'unadjusted':'未调整','baseline_standardization':'基线标准化','crossfit_aipw':'交叉拟合AIPW'}
def csvbytes(rows):
    s=io.StringIO(newline='');keys=list(dict.fromkeys(k for r in rows for k in r));w=csv.DictWriter(s,fieldnames=keys);w.writeheader();w.writerows(rows);return s.getvalue().encode('utf-8-sig')
def render():
    read=lambda n:json.loads((HERE/n).read_bytes())
    desc=read('description.json');bench=read('benchmark-results.json');st=read('structural-results.json');dr=read('dr-results.json');states=['D','I','R','不确定']
    lines=['# LH264：四状态回答与潜在机制的识别','',
    '本轮包含LH263.1维修、四状态全队列描述与遮蔽恢复、双重稳健错设检验，以及一个可复算的结构测量模型。此前的LH262、LH263和2024结果均已查看；本轮是新增回溯诊断，不是盲态预注册。','',
    '**现有数据能够识别字面回答的转换，但不能单独识别其中多少来自潜在状态变化、多少来自回答误差。** 在实际全队列中，字面类别发生变化的比例为10.491%；同一观测表可由一个潜在类别只变化8.218%的模型精确生成。两者的区别来自不可由这两波单一PID指标单独检验的测量假设。','',
    '## 先修复复用接口','',
    '已在保存的旧源码上重现评审反例：标准化子组点值−50个百分点，旧区间却以−20为中心；空匿名输入则成功返回0项核验。维修没有修改旧实证点值或原600次模拟结果。','',
    '标准化区间现在必须显式传入完整拟合人群；跨标准化格和由完整格组成的任何子组均返回`unsupported_standardization_subgroup`，没有完整拟合上下文则返回`fitting_population_required`。这是一项明确的接口限制，不是只重定中心。组外训练者对格均值的估计影响尚未纳入子组方差，因此不发布这种区间。全体原有区间计算保持一致。','',
    '匿名检查现在要求准确的9个唯一群体×方法组合、两侧完整匹配和全部36项核验；空、缺项、不同长度、重复及意外组合均显式报错。详见[LH263.1维修说明](maintenance.md)。','',
    '## 主要描述目标：全体11,009人的四种回答','',
    'D／I／R／不确定均为已观察回答。2020年不确定171人，2022年155人，涉及267人；真正空白为0。R指标的0仅表示“没有明确回答R”，不表示心理层面已知非共和党。固定2020成员定义沿用原研究，不按后来身份筛人。','',
    '下表单位为百分点；B是留存者变化减全队列变化。权重对照使用同一两波commonweight_22，且不把该目标称作全国选民代表。','',
    '| 固定群体 | 全队列n | 留存n | 字面R变化 | 未留存R变化 | B | 固定权重全队列R变化 |','|---|---:|---:|---:|---:|---:|---:|']
    for g in GROUPS:
        get=lambda c,w=False:next(r for r in desc if (r['group'],r['cohort'],r['weighted'])==(g,c,w))
        f,r,o,w=get('full'),get('retained'),get('omitted'),get('full',True)
        lines.append(f"| {G[g]} | {f['n']} | {r['n']} | {f['R_change_pp']:+.3f} | {o['R_change_pp']:+.3f} | {r['R_change_pp']-f['R_change_pp']:+.3f} | {w['R_change_pp']:+.3f} |")
    full=next(r for r in desc if r['group']=='all' and r['cohort']=='full' and not r['weighted'])
    lines += ['', '全体原始转换人数；行是2020、列是2022：','', '| 2020→2022 | D | I | R | 不确定 |','|---|---:|---:|---:|---:|']
    for a in range(4):lines.append('| '+states[a]+' | '+' | '.join(str(v) for v in full['raw_counts'][a])+' |')
    lines += ['', '[144行原始转换表](transitions.csv)含三个固定群体的完整／留存／未留存人数、固定权重质量及两种份额；[描述比较表](description.csv)提供全部18个目标。它们满足每格full=retained+omitted。','',
    '原三态完整案例n=10,742、全体R变化−0.810个百分点；本轮四态全队列n=11,009、变化−0.799。这是不同目标。原resolved界限继续有效，但其“不确定可解析为R或非R”的约定不等于本轮字面目标；不把换目标解释成原界限获得新证据。','',
    '## 四态遮蔽恢复：保持三个固定方法','',
    '6,175名留存者的2022结局用于结局训练，4,834名未留存者的结局在训练文件中为null。全部人用于响应模型，H只含2020信息。18列设计沿用原主效应和少数交互并扩展不确定类别；全体5折、惩罚和裁切预先固定，预测及模型封存后才解封评分。基线标准化使用PID四类×租房与否8格。类别数、矩阵、方向及分母一起扩展，并非只改GLM类别数。','',
    '| 群体 | 方法 | 参考R变化 | 估计R变化 | 恢复误差 | 矩阵半L1差 | 概率矩阵合规 |','|---|---|---:|---:|---:|---:|---|']
    br=[];flows=[]
    for r in bench:
        e,ref=r['estimate'],r['reference'];ok=not e['matrix_outside_probability_domain']
        lines.append(f"| {G[r['group']]} | {M[r['method']]} | {ref['R_change_pp']:+.3f} | {e['R_change_pp']:+.3f} | {r['R_error_pp']:+.3f} | {r['matrix_half_L1_pp']:.3f} | {'是' if ok else '否'} |")
        br.append({'group':r['group'],'method':r['method'],'reference_n':ref['n'],'estimate_n':e['n'],'reference_R_change_pp':ref['R_change_pp'],'estimate_R_change_pp':e['R_change_pp'],'R_error_pp':r['R_error_pp'],'NS_error_pp':r['NS_error_pp'],'any_change_error_pp':r['any_change_error_pp'],'matrix_half_L1_pp':r['matrix_half_L1_pp'],'probability_matrix_valid':ok})
        for k,v in r['flow_error_pp'].items():flows.append({'group':r['group'],'method':r['method'],'direction':k,'reference_pp':ref['flows_pp'][k],'estimate_pp':e['flows_pp'][k],'error_pp':v})
    lines += ['', '全体净变化上标准化比AIPW更接近参考，但整个矩阵的差异次序不同。拉美裔在业组两种调整仍给出错误方向。该组AIPW的I→不确定格为−0.0252个百分点：这是超出概率域的有限样本估计，不是负人数，不能把该矩阵当合法概率分布。没有裁剪、换模型或重调参数；其半L1值仅为带符号估计与参考的代数差异。','',
    '未调整和标准化给出的变化也不是已验证的2024校正。三态与四态恢复练习的目标、类别模型及折划分不同，不能把误差变化完全归因于纳入不确定回答。[重叠与权重集中度](overlap.json)及[108项方向恢复](transition-recovery.csv)保留完整信息；真实数据的经验参考已知，本轮不给它附加抽样置信区间。','',
    '## “双重稳健”只针对有条件的点估计性质','',
    r'在MAR下，给定H，AIPW的条件偏差为 $(1-e/e^*)(m^*-m)$。正确响应或正确结局任一成立时该项为零；组别是H的已知函数时同样成立。代码对8个合成H格做解析期望核验，不依赖模拟看起来接近零。','',
    '另实际运行两种单一正确模型及MNAR反例，每种n=600／2400、120次，共720个数据复制。x、z独立Bernoulli(0.5)，baseline_R为Bernoulli(0.45)；z=1是跨标准化格子组。真结局logit为−1+1.2R20+0.6x+z+xz，真响应logit为−0.4+0.6x−0.9z+0.8xz；MNAR再加1.2R22。正确模型用饱和8格H，错误模型仅截距、x、R20。','',
    '下表为AIPW；覆盖栏是无条件覆盖，未发出的区间也计入分母。全部三方法的偏差、RMSE、SD、bias MCSE、覆盖MCSE及区间可用性见[36行模拟表](dr-summary.csv)。','',
    '| n | 场景 | 群体 | 偏差pp | RMSE | 有效区间／120 | 覆盖 |','|---:|---|---|---:|---:|---:|---:|']
    scenarios={'response_correct_outcome_wrong':'响应正确／结局错误','outcome_correct_response_wrong':'结局正确／响应错误','MNAR_negative_control':'MNAR反例'}
    for r in dr['summaries']:
        if r['method']=='crossfit_aipw':lines.append(f"| {r['n']} | {scenarios[r['scenario']]} | {'全体' if r['group']=='all' else 'z=1'} | {r['bias_pp']:+.3f} | {r['rmse_pp']:.3f} | {r['valid_intervals']} | {100*r['unconditional_coverage']:.1f}% |")
    lines += ['', '两种单一正确情形的较大样本点偏差接近零，但不能因此保证区间：n=2400、结局正确而响应错误的z=1组覆盖仅87.5%（MCSE约3.0个百分点）。n=600子组有许多稀疏方向，区间可用性降低；覆盖差异不能都归于区间中心。MNAR下点偏差约9—10个百分点且大样本覆盖为0，保留为反例。','',
    '标准化子组区间全部标未支持；未调整和AIPW使用大样本贡献方差，单一正确模型下未包含一切nuisance估计影响，覆盖专门用于暴露该限制。交叉拟合不是五次独立验证。相关理论的额外条件见[交叉拟合与正交估计原论文](https://arxiv.org/abs/1608.00060)。','',
    '## 潜在机制：结构映射与观测等价','',
    '令Y0、Y1为四态字面回答，Z0、Z1为四个数学潜标签；Q=diag(π)T是潜在联合表，E0、E1是给定潜标签的回答概率矩阵。假设给定Z0、Z1后两波回答误差独立，则：','',
    r'$$P_{mathrm{obs}}=E_0^	op Q E_1=E_0^	opoperatorname{diag}(pi)T E_1.$$','',
    '一般模型有39个自由参数，而观测4×4表只有15个自由度。参数计数只是警示；真正的非点识别证据是下面不同参数生成同一张实际P。没有拟合一个任意HMM后把其最优值称为真实机制。潜在“不确定”类只是数学标签，不能据此发现认知模糊、情绪或经济焦虑。','',
    r'选取可审查的误分族 $E(epsilon)=(1-epsilon)I+epsilon J/4$；ε是均匀重抽回答的概率，实际错报概率为3ε/4。逆矩阵为 $(I-epsilon J/4)/(1-epsilon)$。由已观测P计算Q，再验证其非负、归一和回投影。','',
    '比较两个预先指定族：仅2022允许误差（E0=I），以及两波测量不变（E0=E1）。ε网格为0到0.20，步长0.005；另以每格非负性的线性／二次不等式确定从0开始的可行段端点。没有裁掉负概率再称精确拟合。','',
    '| 权重 | 误分族 | 可行段ε上端 | ε=0潜在类别改变 | 上端潜在类别改变 | 上端潜在R变化 |','|---|---|---:|---:|---:|---:|']
    sr=[]
    for r in st['models']:
        end=r['witnesses'][-1];lines.append(f"| {'固定2022' if r['weighted'] else '未加权'} | {'仅2022误差' if r['family']=='late_only' else '两波不变'} | {r['connected_feasible_epsilon_max']:.5f} | {r['observed_any_change_pp']:.3f} | {end['latent_any_change_pp']:.3f} | {end['latent_R_change_pp']:+.3f} |")
        for x in r['witnesses']:sr.append({'weighted':r['weighted'],'family':r['family'],'epsilon':x['epsilon'],'latent_R_change_pp':x['latent_R_change_pp'],'latent_any_change_pp':x['latent_any_change_pp'],'projection_max_error':x['max_error'],'retest_disagreement_2022_pp':x['hypothetical_independent_retest_disagreement_2022_pp']})
    lines += ['', '关键例子：未加权、两波测量不变族中，ε=0与ε≈0.01716分别给出潜在类别改变10.491%和8.218%，但回投影得到同一实际观测表，误差小于10⁻¹²。这是观测等价，不是估计回答误差确实为1.716%。','',
    '表中范围仅适用于这两个强约束误分族，不是所有机制的无假设锐界；原始已知标签下的resolved界限也不适用于“已知标签可能错报”的新结构目标。测量不变族中的潜在R变化只按1/(1−ε)缩放，这是假设带来的符号限制。有限样本的零格会限制精确匹配，不能将经验可行性直接变成人口层面机制检验的p值。固定基线定义的子组若依赖Y0，还涉及选择进入子组与潜Z0的关系，因此本轮机制练习只以全体队列为主。','',
    '### 什么新观察能区分这些机制','',
    '已知且满秩的误分类矩阵E0、E1可以直接识别Q；这需要外部验证样本或可信测量锚。另一条路线是在同一潜状态时点获取多个条件独立指标，并核验秩、测量稳定性和标签锚定条件。不能把PID7及其折叠PID3当作两个独立测量，也不能把2024留存标记当作独立心理代理。潜结构可识别性需要这些额外条件，参见[Allman、Matias与Rhodes原论文](https://arxiv.org/abs/0809.5032)。','',
    '本模型还给出具体的可区分预测：若在潜状态不变时做两次条件独立复测，回答不同概率为1.5ε−0.75ε²。无误差见证预测0；未加权两波不变端点预测约2.55%。这是未来测量设计的条件预测，不是已观测复测数据或招募建议。复测若有记忆效应、共同方法误差或真实状态变化，该公式不能照用。普通第三波和更多同源表格不会自动消除这些问题。','',
    '## 验证与交付边界','',
    '原件独立代码完成18张四态目标表的594项人数／权重／分母核查。新四态代码测试覆盖完整数据极限、四态所有方向、遮蔽、结构零、已知测量矩阵恢复、观测等价、负Q保留及DR解析恒等式；维修反例单独测试。匿名ZIP能复算公开表、结构见证和合成模拟；真实四态模型重训仍需官方原件。','',
    'OpenCode Go / Meta Muse 1.3共4次启动：超时、空错误结束、截断输出后，最后一个短矩阵内核完整交付，监督者完成包装、数学边界和独立验证。已报费用合计0.0016292美元，首次超时没有费用回报，不能算零费用。有效内核见matrix4.py；没有将失败输出冒充完整分包。','',
    'GitHub旧运行34298734563在任何测试步骤之前因账户启动限制失败，返回runner_id=0、steps=[]。本地执行证据与远端执行状态分开，不声称GitHub已经成功复现。该限制不改变本轮原件与本地数学核查。','',
    '本轮完成后停止扩模。下一步如果要讨论参与与选票贡献，应另定共同分母及观察规则；如果要识别心理或住房因果机制，则需要新的测量或干预设计，而不是给本次潜标签换一个机制名称。','']
    comparisons=[{k:v for k,v in r.items() if k not in ('raw_counts','matrix','matrix_mass')} for r in desc];trans=[]
    for r in desc:
        if r['weighted']:continue
        w=next(x for x in desc if x['group']==r['group'] and x['cohort']==r['cohort'] and x['weighted'])
        for a in range(4):
            for b in range(4):trans.append({'group':r['group'],'cohort':r['cohort'],'before':states[a],'after':states[b],'n':r['raw_counts'][a][b],'target_n':r['n'],'unweighted_share':r['matrix'][a][b],'fixed_weight_mass':w['matrix_mass'][a][b],'weighted_share':w['matrix'][a][b]})
    return {'report.md':'\n'.join(lines).encode('utf-8'),'description.csv':csvbytes(comparisons),'transitions.csv':csvbytes(trans),'benchmark-comparison.csv':csvbytes(br),'transition-recovery.csv':csvbytes(flows),'structural-witness-summary.csv':csvbytes(sr),'dr-summary.csv':csvbytes(dr['summaries'])}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    for name,b in render().items():
        if a.check:
            if (HERE/name).read_bytes()!=b:raise ValueError('报告或表格不一致：'+name)
        else:(HERE/name).write_bytes(b)
    print(json.dumps({'report':'report.md','description_rows':18,'raw_transition_rows':144,'recoveries':9,'direction_recoveries':108,'structural_witnesses':12,'DR_rows':36,'check':a.check}))
