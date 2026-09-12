"""条件参考、离散区间和多重比较；全为标准库。"""
import bisect,itertools,math,random
from functools import lru_cache
from hypergeom_kernel import hypergeom_pmf
def holm(values):
 order=sorted(range(len(values)),key=values.__getitem__);out=[0.]*len(values);last=0.
 for rank,i in enumerate(order):last=max(last,min(1.,(len(values)-rank)*values[i]));out[i]=last
 return out
def wilson(hits,B):
 z=1.959963984540054;p=hits/B;den=1+z*z/B;center=(p+z*z/(2*B))/den;half=z*math.sqrt(p*(1-p)/B+z*z/(4*B*B))/den
 return [max(0.,center-half),min(1.,center+half)]
def tail_result(hits,B):
 return {'hits':hits,'B':B,'p_plus_one':(hits+1)/(B+1),'MC_se':math.sqrt((hits/B)*(1-hits/B)/B),'MC_Wilson95':wilson(hits,B),'uncertainty_scope':'只量化独立Monte Carlo尾计数误差，不是科学效应区间'}
@lru_cache(maxsize=None)
def hypergeom_cdf(N,K,n):
 pairs=hypergeom_pmf(N,K,n);xs=[x for x,p in pairs];cum=[];s=0.
 for x,p in pairs:s+=p;cum.append(s)
 assert abs(s-1)<1e-10;cum[-1]=1.
 return xs,cum
def hg_draw(rng,N,K,n):
 xs,cdf=hypergeom_cdf(N,K,n);return xs[bisect.bisect_left(cdf,rng.random())]
def margins(table):return [sum(r) for r in table],[sum(r[j] for r in table) for j in range(len(table[0]))]
class FixedMargins:
 def __init__(self,table):
  self.rows,self.cols=margins(table);self.n=sum(self.rows);self.order=sorted(range(len(self.rows)),key=self.rows.__getitem__);self.major=self.order[-1];self.drawn=sum(self.rows)-self.rows[self.major];self.cuts=list(itertools.accumulate(self.cols));self.expected=[[r*c/self.n if self.n else 0. for c in self.cols] for r in self.rows];self.logn=[x*math.log(x) if x else 0. for x in range(self.n+1)];self.constant=self.logn[self.n]-sum(self.logn[x] for x in self.rows+self.cols)
 def draw(self,rng):
  table=[[0]*len(self.cols) for _ in self.rows]
  # 均匀无放回抽取所有非最大组的位置，按预定组大小切段；政策对保持整体。
  sampled=rng.sample(range(self.n),self.drawn);start=0
  for group in self.order[:-1]:
   end=start+self.rows[group]
   for i in sampled[start:end]:table[group][bisect.bisect_right(self.cuts,i)]+=1
   start=end
  for c,n in enumerate(self.cols):table[self.major][c]=n-sum(table[g][c] for g in self.order[:-1])
  return table
 def statistics_numerator(self,table):
  mi=sum(self.logn[n] for row in table for n in row)+self.constant
  tv=sum(abs(n-e) for row,exp in zip(table,self.expected) for n,e in zip(row,exp))/2
  return mi,tv
def quantiles(values):
 s=sorted(values);return {str(q):s[int(q*(len(s)-1))] for q in [0,.025,.25,.5,.75,.95,.975,.99,1.]}
def distribution(values):
 n=len(values);mean=math.fsum(values)/n;sd=math.sqrt(math.fsum((x-mean)**2 for x in values)/(n-1));return {'mean':mean,'sd':sd,'quantiles':quantiles(values)}
@lru_cache(maxsize=None)
def cp_interval(k,n,alpha=.05):
 if n==0:return (0.,1.)
 if not 0<=k<=n or not 0<alpha<1:raise ValueError('二项区间参数非法')
 def cdf(q,p):
  if p<=0:return 1.
  if p>=1:return float(q>=n)
  logs=[math.lgamma(n+1)-math.lgamma(i+1)-math.lgamma(n-i+1)+i*math.log(p)+(n-i)*math.log1p(-p) for i in range(q+1)];top=max(logs);return min(1.,math.exp(top)*sum(math.exp(x-top) for x in logs))
 def solve(q,target):
  lo,hi=0.,1.
  for _ in range(55):
   mid=(lo+hi)/2
   if cdf(q,mid)>target:lo=mid
   else:hi=mid
  return (lo+hi)/2
 return (0. if k==0 else solve(k-1,1-alpha/2),1. if k==n else solve(k,alpha/2))
