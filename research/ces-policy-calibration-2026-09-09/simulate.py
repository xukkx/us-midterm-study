"""预先固定小表的精确零假设与倾斜备择，检验校准而非寻找显著场景。"""
import argparse,bisect,itertools,json,math,random
from collections import Counter
from common import HERE,write,encode
from reference import FixedMargins,hypergeom_cdf,hg_draw,tail_result,wilson
def draw_index(rng,weights):
 u=rng.random()*sum(weights);s=0.
 for i,w in enumerate(weights):
  s+=w
  if u<=s:return i
 return len(weights)-1
def r1_support():
 counts=Counter()
 for seq in set(itertools.permutations([0,0,1,1,2,2,3,3])):
  rows=[seq[:3],seq[3:6],seq[6:]];table=tuple(tuple(row.count(c) for c in range(4)) for row in rows);counts[table]+=1
 entries=sorted(counts);weights=[counts[t]/2520 for t in entries];ref=FixedMargins(entries[0]);stats=[ref.statistics_numerator(t)[0]/8 for t in entries]
 return entries,weights,stats,ref
def run():
 plan=json.loads((HERE/'analysis-plan.json').read_bytes())['simulation'];reps=plan['replications'];B=plan['permutation_draws_per_replication'];entries,w,stats,ref=r1_support();exactp=[sum(weight for s,weight in zip(stats,w) if s>=obs-1e-12) for obs in stats];exactsize=sum(p for p,q in zip(w,exactp) if q<=.05+1e-12);assert exactsize<=.05+1e-12
 output=[]
 for idx,theta in enumerate([0.,math.log(4)]):
  rng=random.Random(plan['seed']+idx);weights=[p*math.exp(theta*sum(t[g][g] for g in range(3))) for t,p in zip(entries,w)];hits=0
  for _ in range(reps):
   i=draw_index(rng,weights);observed=stats[i];tail=sum(ref.statistics_numerator(ref.draw(rng))[0]/8>=observed-1e-12 for _ in range(B));hits+=(tail+1)/(B+1)<=.05
  output.append({'test':'R1_MI','scenario':'exact_fixed_margin_null' if idx==0 else 'fixed_diagonal_tilt_log4','replications':reps,'draws_per_test':B,'rejections':hits,'rejection_rate':hits/reps,'MC_Wilson95':wilson(hits,reps)})
 N,K,n=40,8,10;xs,cdf=hypergeom_cdf(N,K,n);prob=[cdf[i]-(cdf[i-1] if i else 0) for i in range(len(xs))];stat=[x/n-(K-x)/(N-n) for x in xs];exactp2=[sum(p for s,p in zip(stat,prob) if abs(s)>=abs(obs)-1e-12) for obs in stat];size2=sum(p for p,q in zip(prob,exactp2) if q<=.05+1e-12);assert size2<=.05+1e-12
 for idx,odds in enumerate([1.,4.,.25]):
  rng=random.Random(plan['seed']+10+idx);weights=[p*odds**x for p,x in zip(prob,xs)];hits=0
  for _ in range(reps):
   observed=stat[draw_index(rng,weights)];tail=0
   for _ in range(B):x=hg_draw(rng,N,K,n);tail+=abs(x/n-(K-x)/(N-n))>=abs(observed)-1e-12
   hits+=(tail+1)/(B+1)<=.05
  output.append({'test':'R2_absolute_difference','scenario':'equal_probability_null' if odds==1 else 'fixed_conditional_odds_'+str(odds),'replications':reps,'draws_per_test':B,'rejections':hits,'rejection_rate':hits/reps,'MC_Wilson95':wilson(hits,reps)})
 return {'exact_null_sizes_at_05':{'R1_MI':exactsize,'R2_absolute_difference':size2},'R1_enumerated_labeled_assignments':2520,'R1_distinct_tables':len(entries),'scenarios':output,'seed':plan['seed'],'scope':'小表固定边际校准与固定备择功效示例，不代表6175人经验数据的实际功效；保留离散保守性，不据结果调参。'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();r=run()
 if a.check:assert (HERE/'simulation-results.json').read_bytes()==encode(r)
 else:write(HERE/'simulation-results.json',r)
 print(json.dumps(r))
