"""评审的等价路径移植为标准库；概率不合法点保留失败诊断。"""
import argparse,json
from common import HERE,write,encode,sha
from algebra import diag,eye,inverse,mm,transpose,maxerr
from drift_model import *
def point(h,lam):
 if not 0<=lam<=1:raise ValueError('lambda超出范围')
 k=len(h['pi']);q=mm(diag(h['pi']),h['T01']);w=[sum(row[j] for row in q) for j in range(k)];rev=[[x/w[j] for j,x in enumerate(row)] for row in q];u=h['T12'];e=h['E']
 if lam==0:return from_hmm(h)
 m0=[[float(i==j)*(1-lam)+lam*rev[i][j] for j in range(k)] for i in range(k)];m2=[[float(i==j)*(1-lam)+lam*u[i][j] for j in range(k)] for i in range(k)]
 emissions=[mm(transpose(m0),e),copy.deepcopy(e),mm(m2,e)]
 if lam==1:return {'Q':diag(w),'U':eye(k),'E':emissions}
 rp=mm(inverse(m0),rev);up=mm(u,inverse(m2));qp=mm(rp,diag(w))
 return {'Q':qp,'U':up,'E':emissions}
def run():
 src=json.loads((HERE/'lh265-source.json').read_bytes());reference=json.loads((HERE/'reviewer-path-reference.json').read_bytes());counts=src['counts']['all'];results={};comparisons=0
 for name,f in src['models'].items():
  rows=[];h=f['model'];target=f['probabilities'];ll=f['loglik']
  for i in range(101):
   lam=i/100
   try:m=point(h,lam)
   except ValueError as exc:rows.append({'lambda':lam,'status':'inverse_failure','error':str(exc),'model':None});continue
   p=probabilities(m);err=max(abs(a-b) for a,b in zip(target,p));valid=feasible(m);d=drift_metrics(m['E'],middle(m));row={'lambda':lam,'feasible':valid,'status':'attained_feasible_witness' if valid else 'construction_infeasible','minimum_probability':min(values(m)),'projection_max_error':err,'drift':d,'targets':gross(m) if valid else None,'loglik':loglik(counts,p) if valid else None,'model':m if valid else None,'certified_global_bound':False}
   if not valid:row['rejected_Q']=m['Q'];row['rejected_U']=m['U']
   assert err<1e-11
   old=reference[name]['grid'][i];assert valid==old['feasible'];assert abs(d['maximum']-old['max_state_emission_drift_TV'])<1e-9;comparisons+=2
   if valid:assert abs(row['loglik']-ll)<1e-7;assert abs(100*row['targets']['g01']-old['gross01_pct'])<1e-8;assert abs(100*row['targets']['g12']-old['gross12_pct'])<1e-8;comparisons+=3
   rows.append(row)
  results[name]={'rows':rows,'feasible_n':sum(r.get('feasible',False) for r in rows),'failed_n':sum(not r.get('feasible',False) for r in rows),'source_loglik':ll,'maximum_projection_error':max(r.get('projection_max_error',0) for r in rows)}
 assert results['hmm3']['feasible_n']==101 and results['hmm4']['feasible_n']==2
 return {'models':results,'reviewer_reference_checks':comparisons,'source_sha256':sha(HERE/'lh265-source.json'),'scope':'只对已拟合HMM观察法则的等价点；非经验表精确拟合，非全局优化界，未证明网格间处处可行。'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();r=run()
 if a.check:assert (HERE/'equivalence-results.json').read_bytes()==encode(r)
 else:write(HERE/'equivalence-results.json',r)
 print(json.dumps({'feasible':{k:v['feasible_n'] for k,v in r['models'].items()},'reference_checks':r['reviewer_reference_checks']}))
