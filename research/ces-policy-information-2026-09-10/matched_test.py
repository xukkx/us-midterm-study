"""LH269：固定信息集条件关联；完整随机重放与快速存档核验分开。"""
import argparse, bisect, gzip, hashlib, itertools, json, math, random
from pathlib import Path
HERE=Path(__file__).resolve().parent
N_TARGET,DRAWS,SEED=6175,99999,26920260910
PID_MAP=(0,0,0,1,2,2,2,3)
W_LEVELS=tuple(itertools.product(range(3),repeat=2))
PLAN_SHA='bf3c5d331c6f77fbecd2c7d7ef3dee0303d21a91e86f4070490e7e4e7975c823'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def encode(x):return (json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')
def integer(x):return type(x) is int and x>=0
def hg_pmf(n,r,c):
    if not all(integer(x) for x in (n,r,c)) or max(r,c)>n:raise ValueError('超几何参数非法')
    lo,hi=max(0,r+c-n),min(r,c)
    def lc(a,b):return math.lgamma(a+1)-math.lgamma(b+1)-math.lgamma(a-b+1)
    logs=[lc(r,x)+lc(n-r,c-x)-lc(n,c) for x in range(lo,hi+1)]
    top=max(logs);weights=[math.exp(x-top) for x in logs];den=math.fsum(weights)
    return [(x,v/den) for x,v in zip(range(lo,hi+1),weights)]
def tail(k,n):
    if not integer(k) or not integer(n) or n<1 or k>n:raise ValueError('尾计数非法')
    p=k/n;z=1.959963984540054;den=1+z*z/n
    mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return {'hits':k,'B':n,'p_plus_one':(k+1)/(n+1),'MCSE':math.sqrt(p*(1-p)/n),'MC_Wilson95':[max(0.,mid-half),min(1.,mid+half)]}
class FixedMargins:
    def __init__(self,table):
        if not table or not table[0] or any(len(r)!=len(table[0]) or any(not integer(x) for x in r) for r in table):raise ValueError('列联表非法')
        self.t=[list(r) for r in table];self.r=list(map(sum,table));self.c=list(map(sum,zip(*table)));self.n=sum(self.r)
        if self.n<1:raise ValueError('不能抽空层')
        # 转置抽样：Y只有四类，最大Y行补差，减少稳定者的抽样成本。
        self.major=max(range(len(self.c)),key=self.c.__getitem__);self.nonmajor=[i for i,c in enumerate(self.c) if i!=self.major and c]
        self.cuts=list(itertools.accumulate(self.r));self.k=self.n-self.c[self.major]
        self.degenerate=sum(x>0 for x in self.r)<2 or sum(x>0 for x in self.c)<2
        self.lookups=[]
        for r in self.r:
            row=[]
            for c in self.c:row.append(([0.]+[x*math.log(x*self.n/(r*c)) for x in range(1,min(r,c)+1)],[0.5*abs(x-r*c/self.n) for x in range(min(r,c)+1)]))
            self.lookups.append(row)
    def draw(self,rng):
        if self.degenerate:return [r[:] for r in self.t]
        # 有序无放回位置是均匀标签置换的边际；可行表自身并非等概率。
        sample=rng.sample(range(self.n),self.k);out=[[0]*len(self.c) for _ in self.r];pos=0
        for y in self.nonmajor:
            for z in sample[pos:pos+self.c[y]]:out[bisect.bisect_right(self.cuts,z)][y]+=1
            pos+=self.c[y]
        for w,r in enumerate(self.r):out[w][self.major]=r-sum(out[w])
        return out
    def values(self,table):
        if self.degenerate:return 0.,0.
        mi=tv=0.
        for i,row in enumerate(table):
            for j,x in enumerate(row):
                a,b=self.lookups[i][j];mi+=a[x];tv+=b[x]
        return mi/self.n,tv/self.n
    @staticmethod
    def mi(table):return FixedMargins(table).values(table)[0]
    @staticmethod
    def tv(table):return FixedMargins(table).values(table)[1]
    def expectations(self):
        if self.degenerate:return 0.,0.
        mi=tv=0.
        for i,r in enumerate(self.r):
            for j,c in enumerate(self.c):
                a,b=self.lookups[i][j]
                for x,p in hg_pmf(self.n,r,c):mi+=p*a[x]/self.n;tv+=p*b[x]/self.n
        return mi,tv
    def expected_mi(self):return self.expectations()[0]
def make_layers(rows):
    layers={}
    for r in rows:
        h,w,y,n=tuple(r['H']),tuple(r['W']),r['Y'],r['n']
        if len(h)!=2 or not all(type(x) is int for x in h) or not (0<=h[0]<4 and 1<=h[1]<=8) or w not in W_LEVELS or any(type(x) is not int for x in w) or type(y) is not int or not 0<=y<4 or not integer(n):raise ValueError('投影原码或计数非法')
        t=layers.setdefault(h,[[0]*4 for _ in W_LEVELS]);t[W_LEVELS.index(w)][y]+=n
    return [(h,t) for h,t in sorted(layers.items()) if sum(map(sum,t))]
def production_rows():
    if sha(HERE/'analysis-plan.json')!=PLAN_SHA:raise ValueError('研究规格封印改变')
    plan=json.loads((HERE/'analysis-plan.json').read_bytes())
    if sha(HERE/'joint-counts.json')!=plan['input_sha256']['joint-counts.json']:raise ValueError('冻结联合格改变')
    d=json.loads((HERE/'joint-counts.json').read_bytes());out=[]
    for r in d['rows']:
        for k in ('PID20raw','PID22raw','PID24raw'):
            if type(r[k]) is not int or not 1<=r[k]<=8:raise ValueError('PID原码非法')
        out.append({'H':[PID_MAP[r['PID20raw']-1],r['PID22raw']],'W':[r['policy20'],r['policy22']],'Y':PID_MAP[r['PID24raw']-1],'n':r['n']})
    if sum(r['n'] for r in out)!=N_TARGET or sum(r['n'] for r in out if 0 in r['W'])!=7:raise ValueError('目标人数改变')
    return out
def setup(rows):
    layers=make_layers(rows);refs=[FixedMargins(t) for _,t in layers];n=sum(f.n for f in refs)
    return layers,refs,n
def generate(rows,draws=DRAWS,seed=SEED,progress=False):
    layers,refs,n=setup(rows);rng=random.Random(seed);values=[]
    for b in range(draws):
        mi=tv=0.
        for f in refs:
            a,c=f.values(f.draw(rng));mi+=f.n*a/n;tv+=f.n*c/n
        values.append([mi,tv])
        if progress and (b+1)%10000==0:print('已完成条件模拟',b+1,flush=True)
    return values
def summarize(rows,draw_values,seed=SEED):
    layers,refs,n=setup(rows);obs=[0.,0.];expect=[0.,0.]
    for f in refs:
        for j,v in enumerate(f.values(f.t)):obs[j]+=f.n*v/n
        for j,v in enumerate(f.expectations()):expect[j]+=f.n*v/n
    if not draw_values or any(len(x)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v< -1e-12 for v in x) for x in draw_values):raise ValueError('零参考抽样记录非法')
    stats={};B=len(draw_values)
    for j,name in enumerate(('MI','TV')):
        x=[v[j] for v in draw_values];mean=math.fsum(x)/B
        sd=math.sqrt(math.fsum((v-mean)**2 for v in x)/(B-1)) if B>1 else 0.;mc=sd/math.sqrt(B)
        stats[name]={'observed':obs[j],'analytic_null_mean':expect[j],'null':{'mean':mean,'sd':sd,'MCSE_mean':mc,'mean_minus_analytic_in_MCSE':(mean-expect[j])/mc if mc else None},**tail(sum(v>=obs[j]-1e-15 for v in x),B)}
    return {'schema':'LH269-matched-v2','n':n,'draws':B,'seed':seed,'primary':'conditional_MI','auxiliary':'conditional_TV','H':['PID20_4','PID22raw8'],'W':['policy20','policy22'],'Y':'PID24_4','unknown_policy_n':sum(r['n'] for r in rows if 0 in r['W']),'statistics':stats,'layer_n':len(layers),'layers':[{'H':list(h),'n':f.n,'table':t,'W_margins':f.r,'Y_margins':f.c,'zero_W_cells':sum(x==0 for x in f.r),'zero_Y_cells':sum(x==0 for x in f.c),'degenerate':f.degenerate} for (h,t),f in zip(layers,refs)],'uncertainty_scope':'尾概率、Wilson和MCSE描述条件随机参考及有限模拟误差，不是效果区间或因果证据。'}
def calculate(rows,draws=DRAWS,seed=SEED):return summarize(rows,generate(rows,draws,seed),seed)
def synthetic():
    return [{'H':[0,1],'W':list(w),'Y':y,'n':n} for w,y,n in [((0,0),0,3),((0,1),1,2),((1,0),1,2),((1,1),2,3),((2,2),3,2),((0,2),0,1),((2,0),1,1)]]+[{'H':[1,2],'W':[0,0],'Y':0,'n':4},{'H':[1,2],'W':[0,0],'Y':1,'n':2}]
def artifact(rows,values):
    result=summarize(rows,values);result['sources']={n:sha(HERE/n) for n in ('analysis-plan.json','joint-counts.json','matched_test.py')}
    result['generator']='Y最大行补差、有序位置抽样v2；草稿未完成试算未纳入结果';result['null_draws_sha256']=hashlib.sha256(encode(values)).hexdigest()
    if result['n']!=6175 or result['draws']!=99999 or result['layer_n']!=31:raise ValueError('生产规格不符')
    return result
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--check',action='store_true');p.add_argument('--reproduce',action='store_true');a=p.parse_args()
    if sum((a.run,a.check,a.reproduce))!=1:p.error('必须且只能选择一种执行模式')
    rows=production_rows();out=HERE/'matched-test.json';null=HERE/'matched-null.json.gz'
    if a.check:
        values=json.loads(gzip.decompress(null.read_bytes()));expected=artifact(rows,values)
        if out.read_bytes()!=encode(expected):raise ValueError('完整确定性表/存档随机记录摘要不符')
        print('快速核验通过：6175人、31层、99999份存档；未重新抽样');return
    values=generate(rows,progress=True);result=artifact(rows,values);data=encode(result)
    if a.reproduce:
        if out.read_bytes()!=data or gzip.decompress(null.read_bytes())!=encode(values):raise ValueError('完整随机重放与封存结果不符')
        print('完整99999次固定种子随机重放通过')
    else:
        out.write_bytes(data);null.write_bytes(gzip.compress(encode(values),mtime=0));print(json.dumps({'n':result['n'],'statistics':result['statistics']},ensure_ascii=False))
if __name__=='__main__':main()
