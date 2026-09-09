"""联合Q01、后段U及三套发射；所有实际拟合候选须在概率域内。"""
import copy,itertools,math,random
from algebra import diag,eye,inverse,mm,transpose,rank
from drift_kernel import drift_metrics
SEQ=list(itertools.product(range(4),repeat=3))
def normalize(x):
 s=sum(x)
 if s<=0 or any(v<0 or not math.isfinite(v) for v in x):raise ValueError('非法非负质量')
 return [v/s for v in x]
def from_hmm(h):
 return {'Q':mm(diag(h['pi']),h['T01']),'U':copy.deepcopy(h['T12']),'E':[copy.deepcopy(h['E']) for _ in range(3)]}
def middle(m):return [sum(row[j] for row in m['Q']) for j in range(len(m['Q']))]
def gross(m):
 k=len(m['Q']);g01=sum(m['Q'][i][j] for i in range(k) for j in range(k) if i!=j);w=middle(m);g12=sum(w[j]*m['U'][j][l] for j in range(k) for l in range(k) if j!=l)
 return {'g01':g01,'g12':g12,'sum':g01+g12}
def values(m):return [x for row in m['Q']+m['U']+[r for e in m['E'] for r in e] for x in row]
def feasible(m,delta=None,tol=1e-10):
 try:
  k=len(m['Q'])
  if k not in (3,4) or len(m['U'])!=k or len(m['E'])!=3:return False
  if any(len(row)!=k for row in m['Q']+m['U']) or any(len(e)!=k or any(len(row)!=4 for row in e) for e in m['E']):return False
  v=values(m)
  if any(not math.isfinite(x) or x<0 for x in v):return False
  if abs(sum(map(sum,m['Q']))-1)>tol or any(abs(sum(row)-1)>tol for row in m['U']+[r for e in m['E'] for r in e]):return False
  return delta is None or drift_metrics(m['E'],middle(m))['maximum']<=delta+tol
 except (ValueError,TypeError,IndexError,KeyError):return False
def probabilities(m):
 q,u=m['Q'],m['U'];e0,e1,e2=m['E'];k=len(q);result=[]
 # 按(a,b)复用中间前向质量，每次只做K^2+4K计算。
 ue=[[sum(u[j][l]*e2[l][c] for l in range(k)) for c in range(4)] for j in range(k)]
 for a in range(4):
  f=[sum(q[i][j]*e0[i][a] for i in range(k)) for j in range(k)]
  for b in range(4):
   g=[f[j]*e1[j][b] for j in range(k)]
   for c in range(4):result.append(sum(g[j]*ue[j][c] for j in range(k)))
 return result
def loglik(counts,p):
 if len(counts)!=64 or any(type(n)!=int or n<0 for n in counts) or sum(counts)==0:raise ValueError('似然仅接受64格非负整数人数，拒绝权重及有符号矩阵')
 if any(not math.isfinite(v) or v<0 for v in p) or abs(sum(p)-1)>1e-8:raise ValueError('不是有效观察概率')
 return sum(n*math.log(max(v,1e-300)) for n,v in zip(counts,p) if n)
def view_diagnostics(m):
 k=len(m['Q']);pi=[sum(row) for row in m['Q']];w=middle(m);t=[[x/pi[i] for x in row] if pi[i] else eye(k)[i] for i,row in enumerate(m['Q'])]
 return {'ranks':{'E0':rank(m['E'][0]),'E1':rank(m['E'][1]),'E2':rank(m['E'][2]),'T01':rank(t),'T12':rank(m['U'])},'pi':pi,'middle_mass':w,'minimum_probability':min(values(m)),'near_boundary_count_1e8':sum(v<1e-8 for v in values(m))}
def audit(m,counts):
 if not feasible(m):raise ValueError('候选模型概率约束不合规')
 p=probabilities(m)
 return {'loglik':loglik(counts,p),'drift':drift_metrics(m['E'],middle(m)),'targets':gross(m),'diagnostics':view_diagnostics(m),'status':'attained_feasible_witness','certified_global_bound':False,'model':m}
def blend(a,b,step):
 return {'Q':[[x+step*(y-x) for x,y in zip(ra,rb)] for ra,rb in zip(a['Q'],b['Q'])],'U':[[x+step*(y-x) for x,y in zip(ra,rb)] for ra,rb in zip(a['U'],b['U'])],'E':[[[x+step*(y-x) for x,y in zip(ra,rb)] for ra,rb in zip(ea,eb)] for ea,eb in zip(a['E'],b['E'])]}
def shrink_emissions(e,delta,weights=None):
 k=len(e[0]);out=copy.deepcopy(e)
 for j in range(k):
  w=[weights[t][j] if weights else 1. for t in range(3)];s=sum(w)
  center=[sum(w[t]*e[t][j][c] for t in range(3))/s for c in range(4)]
  d=max(sum(abs(e[t][j][c]-e[u][j][c]) for c in range(4))/2 for t,u in [(0,1),(0,2),(1,2)])
  scale=min(1.,delta/d) if d else 1.
  for t in range(3):out[t][j]=[center[c]+scale*(e[t][j][c]-center[c]) for c in range(4)]
 return out
def permute(m,p):
 return {'Q':[[m['Q'][i][j] for j in p] for i in p],'U':[[m['U'][i][j] for j in p] for i in p],'E':[[e[i][:] for i in p] for e in m['E']]}
def random_start(k,kind,seed):
 rng=random.Random(seed)
 if kind.startswith('diffuse'):
  pi=normalize([rng.random()+.2 for _ in range(k)]);t=[normalize([rng.random()+.1 for _ in range(k)]) for _ in range(k)];e=[normalize([rng.random()+.1 for _ in range(4)]) for _ in range(k)]
 elif kind.startswith('asymmetric'):
  pi=normalize([rng.random()**2+.05 for _ in range(k)]);t=[normalize([.5*(i==j)+rng.random()**2 for j in range(k)]) for i in range(k)];e=[normalize([.6*(j==(i+1)%4)+rng.random()**2 for j in range(4)]) for i in range(k)]
 else:
  pi=normalize([.001 if i==k-1 else rng.random()+.2 for i in range(k)]);t=[normalize([2.*(i==j)+.001+rng.random()*.02 for j in range(k)]) for i in range(k)];e=[normalize([1.*(i==j)+.0001+rng.random()*.01 for j in range(4)]) for i in range(k)]
 u=[normalize([rng.random()*.3+(i==j) for j in range(k)]) for i in range(k)]
 return {'Q':mm(diag(pi),t),'U':u,'E':[copy.deepcopy(e) for _ in range(3)]}
