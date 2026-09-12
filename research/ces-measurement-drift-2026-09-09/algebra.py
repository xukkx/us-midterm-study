"""小矩阵标准库代数；显式拒绝秩不足，不使用截断逆。"""
from itertools import combinations
from math import fsum

def transpose(a):return list(map(list,zip(*a)))
def mm(a,b):return [[fsum(x*y for x,y in zip(row,col)) for col in zip(*b)] for row in a]
def eye(n):return [[float(i==j) for j in range(n)] for i in range(n)]
def diag(x):return [[v if i==j else 0. for j in range(len(x))] for i,v in enumerate(x)]
def inverse(a,tol=1e-12):
 n=len(a);r=[list(row)+e for row,e in zip(a,eye(n))]
 if any(len(row)!=n for row in a):raise ValueError('矩阵不是方阵')
 for j in range(n):
  k=max(range(j,n),key=lambda k:abs(r[k][j]))
  if abs(r[k][j])<tol:raise ValueError('秩不足或数值退化')
  r[j],r[k]=r[k],r[j];v=r[j][j];r[j]=[x/v for x in r[j]]
  for k in range(n):
   if k!=j:
    v=r[k][j];r[k]=[x-v*y for x,y in zip(r[k],r[j])]
 return [row[n:] for row in r]
def determinant(a):
 r=[row[:] for row in a];d=1.;n=len(a)
 for j in range(n):
  k=max(range(j,n),key=lambda k:abs(r[k][j]))
  if abs(r[k][j])<1e-16:return 0.
  if k!=j:r[j],r[k]=r[k],r[j];d=-d
  v=r[j][j];d*=v
  for k in range(j+1,n):
   f=r[k][j]/v
   for q in range(j+1,n):r[k][q]-=f*r[j][q]
 return d
def left_inverse(a):return mm(inverse(mm(transpose(a),a)),transpose(a))
def maxerr(a,b):return max(abs(x-y) for ra,rb in zip(a,b) for x,y in zip(ra,rb))
def rank(a,tol=1e-9):
 r=[row[:] for row in a];i=0
 for j in range(len(r[0])):
  k=max(range(i,len(r)),key=lambda k:abs(r[k][j]))
  if abs(r[k][j])<=tol:continue
  r[i],r[k]=r[k],r[i];v=r[i][j]
  for k in range(i+1,len(r)):
   f=r[k][j]/v
   for q in range(j,len(r[0])):r[k][q]-=f*r[i][q]
  i+=1
  if i==len(r):break
 return i
def condition_inf(a):
 try:return max(sum(abs(x) for x in row) for row in a)*max(sum(abs(x) for x in row) for row in inverse(a))
 except ValueError:return None
def polyval(c,x):
 v=0.
 for z in c:v=v*x+z
 return v
def real_roots(c,lo,hi):
 # 导数递归隔离简单实根；本研究的谱值有界于收缩向量的最小/最大值。
 if len(c)==2:return [-c[1]/c[0]] if lo < -c[1]/c[0] < hi else []
 critical=real_roots([c[i]*(len(c)-1-i) for i in range(len(c)-1)],lo,hi)
 out=[]
 for a,b in zip([lo]+critical,critical+[hi]):
  fa,fb=polyval(c,a),polyval(c,b)
  if fa*fb>=0:continue
  for _ in range(65):
   m=(a+b)/2;fm=polyval(c,m)
   if fa*fm<=0:b=m
   else:a=m;fa=fm
  out.append((a+b)/2)
 return out
def eig_simple(a,lo,hi):
 n=len(a);b=eye(n);coeff=[1.]
 for k in range(1,n+1):
  b=mm(a,b);c=-fsum(b[i][i] for i in range(n))/k;coeff.append(c)
  for i in range(n):b[i][i]+=c
 roots=real_roots(coeff,lo,hi)
 if len(roots)!=n or min((abs(x-y) for i,x in enumerate(roots) for y in roots[i+1:]),default=1)<1e-7:raise ValueError('谱根重复或不能稳定隔离')
 vectors=[]
 for lam in roots:
  h=[[a[i][j]-lam*(i==j) for j in range(n)] for i in range(n)]
  # adjugate的最长列是零空间向量；不需未知参数参与恢复。
  cols=[]
  for q in range(n):
   cols.append([(-1)**(q+i)*determinant([[h[r][c] for c in range(n) if c!=i] for r in range(n) if r!=q]) for i in range(n)])
  v=max(cols,key=lambda x:sum(z*z for z in x));s=sum(v)
  if abs(s)<1e-12:raise ValueError('特征向量归一失败')
  vectors.append([x/s for x in v])
 return roots,transpose(vectors)

def spectral_views(p,k):
 """只用4×4×4观测分布恢复w,A,B,C，标签由谱排序决定。"""
 m=len(p);p01=[[sum(p[a][b]) for b in range(m)] for a in range(m)]
 candidates=[]
 for rows in combinations(range(m),k):
  for cols in combinations(range(m),k):
   sub=[[p01[a][b] for b in cols] for a in rows];candidates.append((abs(determinant(sub)),rows,cols,sub))
 value,rows,cols,sub=max(candidates)
 if value<1e-12:raise ValueError('观测边际秩不足')
 si=inverse(sub);eta=[.13,.37,.71,1.19]
 mix=[[sum(eta[c]*p[a][b][c] for c in range(m)) for b in cols] for a in rows]
 roots,ar=eig_simple(mm(mix,si),min(eta)-.01,max(eta)+.01)
 a=mm(mm([[p01[i][j] for j in cols] for i in range(m)],si),ar)
 for j in range(k):
  s=sum(a[i][j] for i in range(m))
  for i in range(m):a[i][j]/=s
 la=left_inverse(a);p0=[[sum(row)] for row in p01];w=[r[0] for r in mm(la,p0)]
 if min(w)<=0:raise ValueError('非正潜在质量')
 b=transpose([[x/w[j] for x in row] for j,row in enumerate(mm(la,p01))])
 ar=[[a[i][j] for j in range(k)] for i in rows];ari=inverse(ar)
 c=[]
 for t in range(m):
  d=mm(mm(ari,mm([[p[i][j][t] for j in cols] for i in rows],si)),ar)
  c.append([d[j][j] for j in range(k)])
 return w,a,b,c

def recover_hmm(p,k):
 w,a,b,c=spectral_views(p,k);e=transpose(b);le=left_inverse(b)
 q=mm(mm(le,a),diag(w));pi=[sum(row) for row in q]
 t01=[[x/pi[i] for x in row] for i,row in enumerate(q)];t12=transpose(mm(le,c))
 values=pi+[x for z in (e,t01,t12) for row in z for x in row]
 if min(values)<-1e-7:raise ValueError('恢复参数超出HMM概率域')
 return {'pi':pi,'T01':t01,'T12':t12,'E':e}
