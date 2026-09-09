"""三时点整数频数似然；不同时间转移、共同发射与静态时变发射。"""
import itertools,math,random
from algebra import transpose,mm,diag
SEQ=list(itertools.product(range(4),repeat=3));FLOOR=1e-12
def norm(x):
 s=sum(x)
 if s<=0:raise ValueError('空概率质量')
 z=[max(FLOOR,v/s) for v in x];s=sum(z);return [v/s for v in z]
def validate_counts(counts):
 if len(counts)!=64 or any(type(n)!=int or n<0 for n in counts) or sum(counts)==0:raise ValueError('要求64个非负整数频数且总数大于0；拒绝调查权重/带符号表')
def initial(k,rng):
 e=[norm([rng.random()*.15+(1. if j==i else 0.) for j in range(4)]) for i in range(k)]
 t=lambda:[norm([rng.random()*.12+(1. if i==j else 0.) for j in range(k)]) for i in range(k)]
 return {'pi':norm([rng.random()+.2 for _ in range(k)]),'T01':t(),'T12':t(),'E':e}
def fb(model,y):
 pi,t,u,e=(model[x] for x in ('pi','T01','T12','E'));k=len(pi);a,b,c=y
 f=[pi[i]*e[i][a] for i in range(k)]
 g=[sum(f[i]*t[i][j] for i in range(k))*e[j][b] for j in range(k)]
 h=[e[j][b]*sum(u[j][l]*e[l][c] for l in range(k)) for j in range(k)]
 prob=sum(g[j]*u[j][l]*e[l][c] for j in range(k) for l in range(k))
 if prob<=0:raise ValueError('序列概率为零')
 q01=[[f[i]*t[i][j]*h[j]/prob for j in range(k)] for i in range(k)]
 q12=[[g[j]*u[j][l]*e[l][c]/prob for l in range(k)] for j in range(k)]
 return prob,q01,q12
def tensor(model):
 pi,t,u,e=(model[x] for x in ('pi','T01','T12','E'));k=len(pi)
 # 分包的前向概率内核与监督者独立后验内核共享数学定义。
 from probability_kernel import joint
 return [joint(pi,t,u,e,y) for y in SEQ]
def tensor3(flat):return [[[flat[16*a+4*b+c] for c in range(4)] for b in range(4)] for a in range(4)]
def static_map(model):
 pi,t,u,e=(model[x] for x in ('pi','T01','T12','E'))
 w=[sum(pi[i]*t[i][j] for i in range(len(pi))) for j in range(len(pi))]
 a=mm(mm(mm(transpose(e),diag(pi)),t),diag([1/v for v in w]))
 c=mm(transpose(e),transpose(u))
 return {'w':w,'emissions':[transpose(a),e,transpose(c)]}
def static_tensor(m):
 w=m['w'];a,b,c=m['emissions'];return [sum(w[j]*a[j][x]*b[j][y]*c[j][z] for j in range(len(w))) for x,y,z in SEQ]
def likelihood(counts,p):return sum(n*math.log(max(q,1e-300)) for n,q in zip(counts,p) if n)
def summary(p):
 return {'gross01':sum(q for (a,b,c),q in zip(SEQ,p) if a!=b),'gross12':sum(q for (a,b,c),q in zip(SEQ,p) if b!=c),'return':sum(q for (a,b,c),q in zip(SEQ,p) if a==c and a!=b),'R_net01':sum(q*((b==2)-(a==2)) for (a,b,c),q in zip(SEQ,p)),'R_net12':sum(q*((c==2)-(b==2)) for (a,b,c),q in zip(SEQ,p))}
def latent_summary(m):
 pi,t,u=(m[x] for x in ('pi','T01','T12'));w=[sum(pi[i]*t[i][j] for i in range(len(pi))) for j in range(len(pi))]
 return {'gross01':1-sum(pi[i]*t[i][i] for i in range(len(pi))),'gross12':1-sum(w[i]*u[i][i] for i in range(len(pi))),'return':sum(pi[i]*t[i][j]*u[j][i] for i in range(len(pi)) for j in range(len(pi)) if i!=j)}
def fit_hmm(counts,k,seed,starts=12,iterations=600,tol=1e-8,gross=None,extra=None):
 validate_counts(counts);n=sum(counts);ledger=[];best=None;data=[(y,c) for y,c in zip(SEQ,counts) if c]
 for start in range(starts):
  rng=random.Random(seed+start*1009);m=initial(k,rng)
  if start==0 and extra:m={key:([r[:] for r in val] if isinstance(val[0],list) else val[:]) for key,val in extra.items()}
  if gross is not None:
   for i in range(k):
    off=sum(m['T01'][i][j] for j in range(k) if i!=j)
    m['T01'][i]=[1-gross if j==i else gross*m['T01'][i][j]/off for j in range(k)]
  old=likelihood(counts,tensor(m));converged=False;decreases=0
  for it in range(iterations):
   q=[[0.]*k for _ in range(k)];r=[[0.]*k for _ in range(k)];em=[[0.]*4 for _ in range(k)]
   for y,cnt in data:
    p,x,z=fb(m,y)
    for i in range(k):
     em[i][y[0]]+=cnt*sum(x[i]);em[i][y[1]]+=cnt*sum(z[i]);em[i][y[2]]+=cnt*sum(z[j][i] for j in range(k))
     for j in range(k):q[i][j]+=cnt*x[i][j];r[i][j]+=cnt*z[i][j]
   if gross is not None:
    d=sum(q[i][i] for i in range(k));o=sum(q[i][j] for i in range(k) for j in range(k) if i!=j)
    q=[[((1-gross)*q[i][j]/d if i==j else gross*q[i][j]/o if o else 0.) for j in range(k)] for i in range(k)]
   pi=norm([sum(row) for row in q]);t=[]
   for row in q:
    s=sum(row);t.append([v/s for v in row] if gross is not None else norm(row))
   new={'pi':pi,'T01':t,'T12':[norm(row) for row in r],'E':[norm(row) for row in em]}
   ll=likelihood(counts,tensor(new));decreases+=int(ll<old-1e-7)
   if abs(ll-old)/n<tol:converged=True;m=new;old=ll;break
   m=new;old=ll
  row={'start':start,'loglik':old,'iterations':it+1,'converged':converged,'likelihood_decreases':decreases,'latent':latent_summary(m)};ledger.append(row)
  if best is None or old>best['loglik']:best={'model':m,'loglik':old,'converged':converged,'iterations':it+1}
 best['starts']=ledger;return best
def fit_static(counts,k,seed,starts=12,iterations=600,tol=1e-8,extra=None):
 validate_counts(counts);n=sum(counts);best=None;ledger=[];data=[(y,c) for y,c in zip(SEQ,counts) if c]
 for start in range(starts):
  rng=random.Random(seed+1009*start);h=initial(k,rng);m={'w':h['pi'],'emissions':[initial(k,rng)['E'] for _ in range(3)]}
  if start==0 and extra:m=extra
  old=likelihood(counts,static_tensor(m));conv=False;decreases=0
  for it in range(iterations):
   mass=[0.]*k;em=[[[0.]*4 for _ in range(k)] for _ in range(3)]
   for y,cnt in data:
    raw=[m['w'][i]*math.prod(m['emissions'][t][i][y[t]] for t in range(3)) for i in range(k)];s=sum(raw)
    for i in range(k):
     v=cnt*raw[i]/s;mass[i]+=v
     for t in range(3):em[t][i][y[t]]+=v
   m={'w':norm(mass),'emissions':[[norm(row) for row in e] for e in em]};ll=likelihood(counts,static_tensor(m));decreases+=int(ll<old-1e-7)
   if abs(ll-old)/n<tol:conv=True;old=ll;break
   old=ll
  ledger.append({'start':start,'loglik':old,'iterations':it+1,'converged':conv,'likelihood_decreases':decreases})
  if best is None or old>best['loglik']:best={'model':m,'loglik':old,'converged':conv,'iterations':it+1}
 best['starts']=ledger;return best
def fit_observed(counts):
 validate_counts(counts);pi=[0.]*4;t=[[0.]*4 for _ in range(4)];u=[[0.]*4 for _ in range(4)]
 for (a,b,c),n in zip(SEQ,counts):pi[a]+=n;t[a][b]+=n;u[b][c]+=n
 # 零支持条件行使用均匀分布，概率下限只为计算与留出评分。
 t=[norm(row) if sum(row) else [.25]*4 for row in t];u=[norm(row) if sum(row) else [.25]*4 for row in u];pi=norm(pi)
 p=[pi[a]*t[a][b]*u[b][c] for a,b,c in SEQ]
 return {'model':{'pi':pi,'T01':t,'T12':u},'probabilities':p,'loglik':likelihood(counts,p)}
def sample(p,n,rng):
 counts=[0]*64
 for i in rng.choices(range(64),weights=p,k=n):counts[i]+=1
 return counts
