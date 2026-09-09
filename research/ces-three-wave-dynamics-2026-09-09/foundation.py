"""两波等价见证与标签测量误差预算；均非总体置信区间。"""
import math
from algebra import eye,diag,mm,transpose,maxerr
def budgets(g,delta,a0,a1):
 if any(isinstance(x,bool) or not math.isfinite(x) for x in [g,delta,a0,a1]) or not 0<=g<=1 or not -1<=delta<=1 or not 0<=a0<=1 or not 0<=a1<=1:raise ValueError('非法误差预算或目标')
 a=a0+a1
 return {'gross':[max(0,g-a),min(1,g+a)],'R_net':[max(-1,delta-a),min(1,delta+a)],'interpretation':'有共同标签与端点错误概率上限的保守外界；不是锐界或置信区间'}
def equivalent(p):
 if len(p)!=4 or any(len(r)!=4 for r in p) or any(not math.isfinite(x) or x<0 for r in p for x in r) or abs(sum(map(sum,p))-1)>1e-10:raise ValueError('非法观察概率表')
 marginal=[sum(r) for r in p]
 # 零质量状态的发射不受观测约束；采用单位行作可行见证。
 e1=[[x/marginal[i] for x in row] if marginal[i] else eye(4)[i] for i,row in enumerate(p)]
 q=diag(marginal);reconstructed=mm(q,e1);delta=sum(p[i][2]-p[2][i] for i in range(4));gross=1-sum(p[i][i] for i in range(4))
 return {'P':p,'identity_measurement':{'E0':eye(4),'E1':eye(4),'Q':p,'latent_gross':gross,'latent_R_net':delta},'zero_latent_change':{'E0':eye(4),'E1':e1,'Q':q,'latent_gross':0.,'latent_R_net':0.,'max_reconstruction_error':maxerr(p,reconstructed)},'asymmetry_max':maxerr(p,transpose(p)),'passes_symmetry_necessary_condition':maxerr(p,transpose(p))<1e-12,'budget_rows':[dict(per_wave_budget=a,**budgets(gross,delta,a,a)) for a in [0,.005,.02]],'symmetry_interpretation':'不对称排除精确拟合经验表的共同独立测量+零潜变化模型；对称只是必要条件，不足以证明相容，也不自动构成人口统计拒绝。'}
