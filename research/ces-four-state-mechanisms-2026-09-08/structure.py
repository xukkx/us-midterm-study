"""观测等价见证与受限误分族敏感性；不报告无假设心理机制锐界。"""
import argparse,json,math
from common import *
from latent_kernel import reconstruct

def boundary(P,family,cap=.2):
    if family not in ('late_only','invariant') or not 0<cap<1:raise ValueError('结构族或上限非法')
    reconstruct(P,0,0)
    rows=[math.fsum(r) for r in P];cols=[math.fsum(P[i][j] for i in range(4)) for j in range(4)];limit=cap
    for i in range(4):
        for j in range(4):
            c=P[i][j]
            if family=='late_only':
                if rows[i]>0:limit=min(limit,4*c/rows[i])
            else:
                a=1/16;b=-(rows[i]+cols[j])/4;disc=b*b-4*a*c
                # 正二次项：负集合只能在两个实根之间。从0起可行段的首次负值位置可直接求。
                if disc>0:
                    first=(-b-math.sqrt(disc))/(2*a);last=(-b+math.sqrt(disc))/(2*a)
                    if last>0 and first<limit:limit=max(0.,first)
    return max(0.,limit)
def evaluate(P,epsilon,family):
    v=reconstruct(P,0 if family=='late_only' else epsilon,epsilon)
    if not v['feasible']:return {'epsilon':epsilon,'feasible':False}
    Q=v['Q'];pi=[math.fsum(r) for r in Q];T=[[x/pi[i] for x in row] if pi[i]>1e-14 else None for i,row in enumerate(Q)]
    e0=0 if family=='late_only' else epsilon
    return {'epsilon':epsilon,'per_wave_misreport_probability':.75*epsilon,'feasible':True,'latent_R_change_pp':100*v['latent_R_change'],'latent_any_change_pp':100*v['gross_change'],'pi':pi,'transition':T,
            'hypothetical_independent_retest_disagreement_2020_pp':100*(1.5*e0-.75*e0*e0),
            'hypothetical_independent_retest_disagreement_2022_pp':100*(1.5*epsilon-.75*epsilon*epsilon),**v}
def compute(description):
    results=[]
    for weighted in (False,True):
        r=next(x for x in description if x['group']=='all' and x['cohort']=='full' and x['weighted']==weighted);P=r['matrix']
        for family in ('late_only','invariant'):
            limit=boundary(P,family);witnesses=[evaluate(P,e,family) for e in [0,limit/2,limit]]
            if not all(x['feasible'] and x['max_error']<1e-12 for x in witnesses):raise ValueError('结构见证不满足原观测')
            grid=[evaluate(P,i/200,family) for i in range(41)]
            results.append({'weighted':weighted,'family':family,'observed_R_change_pp':r['R_change_pp'],'observed_any_change_pp':r['any_change_pp'],'connected_feasible_epsilon_max':limit,'witnesses':witnesses,'grid':grid,'maximum_witness_projection_error':max(x['max_error'] for x in witnesses),
                            'scope':'只考察明示均匀误分类族；端点是该族从0连通可行段，不是全部潜机制的锐界。固定权重矩阵不称总体代表。'})
    return {'models':results,'structural_map':'P=E0^T diag(pi) T E1','free_model_parameters':39,'observable_joint_degrees_of_freedom':15,'identification_claim':'非点识别由不同潜转换和测量参数的相同观测见证证明；参数计数只作提示。','conditional_independence':'给定Z0,Z1，各波回答误差独立；未在数据中证实。','latent_state_semantics':'四潜态按回答标签锚定，仅作数学类别；不确定潜态不是已发现的心理机制。'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();v=compute(json.loads((HERE/'description.json').read_bytes()));b=encode(v)
    if a.check:
        if (HERE/'structural-results.json').read_bytes()!=b:raise ValueError('结构模型复算不符')
    else:(HERE/'structural-results.json').write_bytes(b)
    print(json.dumps({'models':len(v['models']),'contrasts':[{'weighted':r['weighted'],'family':r['family'],'epsilon_max':r['connected_feasible_epsilon_max'],'observed_gross':r['observed_any_change_pp'],'latent_gross_at_endpoint':r['witnesses'][-1]['latent_any_change_pp'],'latent_R_at_endpoint':r['witnesses'][-1]['latent_R_change_pp']} for r in v['models']]},ensure_ascii=False))
