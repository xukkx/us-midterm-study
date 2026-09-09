"""不导入拟合内核的独立数值审计，以及封印/载荷检查。"""
import argparse,csv,hashlib,io,itertools,json,math
from common import HERE,sha,encode,write
from algebra import rank
def verify():
 r=json.loads((HERE/'results.json').read_bytes());d=json.loads((HERE/'trajectories.json').read_bytes());checks=0
 def check(ok):
  nonlocal checks
  if not ok:raise ValueError(f'独立核验失败：{checks+1}')
  checks+=1
 check(sha(HERE/'analysis-plan.json')==json.loads((HERE/'analysis-plan-seal.json').read_bytes())['sha256'])
 for key,name in [('exact_sha256','exact-results.json'),('recovery_sha256','recovery-results.json'),('trajectories_sha256','trajectories.json')]:check(sha(HERE/name)==r['gates'][key])
 check(d['sequences']==[list(y) for y in itertools.product(range(4),repeat=3)])
 check(len(d['fold_counts'])==5 and all(len(row)==64 for row in d['fold_counts']))
 check(all(sum(row[i] for row in d['fold_counts'])==d['counts']['all'][i] for i in range(64)))
 for g,counts in d['counts'].items():
  check(len(counts)==64 and all(type(n)==int and n>=0 for n in counts));check(sum(counts)==d['denominators'][g]['complete'])
 diagnostics={}
 for name,f in r['fits'].items():
  p=f['probabilities'];check(len(p)==64 and min(p)>=0 and abs(sum(p)-1)<1e-9)
  check(abs(sum(n*math.log(max(x,1e-300)) for n,x in zip(d['counts']['all'],p) if n)-f['loglik'])<1e-8)
  if name.startswith('hmm'):
   m=f['model'];k=len(m['pi'])
   for row in [m['pi']]+m['E']+m['T01']+m['T12']:check(min(row)>=0 and abs(sum(row)-1)<1e-9)
   independent=[]
   for a,b,c in itertools.product(range(4),repeat=3):independent.append(sum(m['pi'][i]*m['T01'][i][j]*m['T12'][j][l]*m['E'][i][a]*m['E'][j][b]*m['E'][l][c] for i,j,l in itertools.product(range(k),repeat=3)))
   check(max(abs(x-y) for x,y in zip(p,independent))<1e-12)
   static=f['static_equivalence_witness'];e0,e1,e2=static['emissions']
   static_p=[sum(static['w'][j]*e0[j][a]*e1[j][b]*e2[j][c] for j in range(k)) for a,b,c in itertools.product(range(4),repeat=3)]
   check(max(abs(x-y) for x,y in zip(p,static_p))<1e-12)
   check(abs(f['latent']['gross01']-sum(m['pi'][i]*m['T01'][i][j] for i,j in itertools.product(range(k),repeat=2) if i!=j))<1e-10)
   diagnostics[name]={'view_ranks':[rank(e0),rank(e1),rank(e2)],'min_pi':min(m['pi']),'min_middle_mass':min(static['w']),'minimum_parameter':min(x for row in m['E']+m['T01']+m['T12'] for x in row),'boundary_parameter_count_1e_8':sum(x<1e-8 for row in m['E']+m['T01']+m['T12'] for x in row),'all_start_likelihood_monotone':all(x['likelihood_decreases']==0 for x in f['starts'])}
  if 'starts' in f:check(len(f['starts'])==12 and all(x['likelihood_decreases']==0 for x in f['starts']))
 check(len(r['cv'])==25 and len({(x['fold'],x['model']) for x in r['cv']})==25)
 for row in r['cv']:
  p=row['probabilities'];c=d['fold_counts'][row['fold']];n=sum(c);check(row['n']==n)
  score=sum(v*math.log(max(p[i]/sum(p[(i//4)*4:(i//4)*4+4]),1e-300)) for i,v in enumerate(c) if v)/n
  check(abs(score-row['last_wave_conditional_log_score'])<1e-12)
 for row in r['profile']:check(row['constraint_error']<1e-9 and all(x['likelihood_decreases']==0 for x in row['starts']))
 csv_rows=list(csv.DictReader((HERE/'trajectory-comparison.csv').open(encoding='utf-8',newline='')));check(len(csv_rows)==64)
 for i,row in enumerate(csv_rows):
  check(int(row['observed_n'])==d['counts']['all'][i]);check(all(abs(float(row[name])-r['n']*f['probabilities'][i])<1e-9 for name,f in r['fits'].items()))
 ref=json.loads((HERE/'two-wave-reference.json').read_bytes());b=json.loads((HERE/'measurement-results.json').read_bytes());p=[[v/ref['n'] for v in row] for row in ref['counts']];check(p==b['P'])
 m=b['zero_latent_change'];check(max(abs(sum(m['Q'][i][j]*m['E1'][j][k] for j in range(4))-p[i][k]) for i in range(4) for k in range(4))<1e-12)
 return {'checks':checks,'passed':True,'diagnostics':diagnostics,'note':'独立枚举概率、潜质量、整人折、CSV与输入封印；数值秩是诊断，不是实证假设证明。'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();r=verify()
 if a.check:assert (HERE/'verification.json').read_bytes()==encode(r)
 else:write(HERE/'verification.json',r)
 if (HERE/'checksums.json').exists():
  checks=json.loads((HERE/'checksums.json').read_bytes())
  for name,h in checks.items():
   p=(HERE/name).resolve()
   if not p.is_relative_to(HERE.resolve()) or sha(p)!=h:raise ValueError('载荷路径或哈希不符：'+name)
 print(json.dumps(r,ensure_ascii=False))
