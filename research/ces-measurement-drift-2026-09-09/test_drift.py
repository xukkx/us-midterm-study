"""独立穷举、标签、概率域、约束和失败状态测试。"""
import itertools,json,random,unittest
from common import HERE
from drift_model import *
from equivalence import point,run
from profile import fit,extreme
class DriftTests(unittest.TestCase):
 def test_independent_probability_enumeration(self):
  for k in [3,4]:
   m=random_start(k,'diffuse',k);q,u=m['Q'],m['U'];e0,e1,e2=m['E']
   direct=[sum(q[i][j]*u[j][l]*e0[i][a]*e1[j][b]*e2[l][c] for i,j,l in itertools.product(range(k),repeat=3)) for a,b,c in SEQ]
   self.assertLess(max(abs(a-b) for a,b in zip(direct,probabilities(m))),1e-14)
 def test_muse_drift_independent(self):
  m=random_start(4,'asymmetric',18);m['E'][2]=random_start(4,'diffuse',44)['E'][0];w=middle(m);r=drift_metrics(m['E'],w)
  independent=[max(sum(abs(m['E'][t][k][j]-m['E'][u][k][j]) for j in range(4))/2 for t,u in [(0,1),(0,2),(1,2)]) for k in range(4)]
  self.assertLess(max(abs(x-y) for x,y in zip(independent,r['per_state'])),1e-14);self.assertAlmostEqual(r['weighted_average'],sum(x*y for x,y in zip(w,independent)))
 def test_common_permutation_only(self):
  m=random_start(3,'asymmetric',20);p=[2,0,1];n=permute(m,p)
  self.assertLess(max(abs(x-y) for x,y in zip(probabilities(m),probabilities(n))),1e-14);self.assertAlmostEqual(gross(m)['sum'],gross(n)['sum']);self.assertAlmostEqual(drift_metrics(m['E'],middle(m))['maximum'],drift_metrics(n['E'],middle(n))['maximum'])
 def test_independent_time_permutation_changes_latent_target(self):
  e=[[.9,.05,.04,.01],[.05,.9,.04,.01],[.04,.05,.9,.01]];m={'Q':diag([.4,.2,.4]),'U':eye(3),'E':[copy.deepcopy(e) for _ in range(3)]};p=[1,2,0];n=copy.deepcopy(m);n['E'][2]=[e[i] for i in p];n['U']=[[m['U'][i][j] for j in p] for i in range(3)]
  self.assertLess(max(abs(x-y) for x,y in zip(probabilities(m),probabilities(n))),1e-14);self.assertEqual(gross(m)['g12'],0);self.assertAlmostEqual(gross(n)['g12'],1);self.assertGreater(drift_metrics(n['E'],middle(n))['maximum'],.8)
 def test_shrink_and_convex_feasibility(self):
  m=random_start(3,'diffuse',10);m['E'][2]=random_start(3,'asymmetric',19)['E'][0]
  for delta in [0,.01,.1]:
   a=copy.deepcopy(m);a['E']=shrink_emissions(a['E'],delta);self.assertTrue(feasible(a,delta));b=random_start(3,'diffuse',30);self.assertTrue(feasible(blend(a,b,.4),delta))
 def test_signed_or_weight_counts_rejected(self):
  m=random_start(3,'diffuse',2);p=probabilities(m)
  for c in [[-1]+[1]*63,[.5]*64,[0]*64,[True]*64]:
   with self.assertRaises(ValueError):loglik(c,p)
  m['Q'][0][0]=-1e-12;self.assertFalse(feasible(m))
 def test_review_paths_and_failures(self):
  r=run();self.assertEqual(r['models']['hmm3']['feasible_n'],101);self.assertEqual(r['models']['hmm4']['failed_n'],99)
  for row in r['models']['hmm4']['rows'][1:-1]:self.assertIsNone(row['targets']);self.assertIsNone(row['model']);self.assertEqual(row['status'],'construction_infeasible')
 def test_endpoints_same_law_different_dynamics(self):
  src=json.loads((HERE/'lh265-source.json').read_bytes())
  for k in [3,4]:
   h=src['models'][f'hmm{k}']['model'];a=point(h,0);b=point(h,1)
   self.assertTrue(feasible(a));self.assertTrue(feasible(b));self.assertEqual(gross(b)['sum'],0);self.assertLess(max(abs(x-y) for x,y in zip(probabilities(a),probabilities(b))),1e-12)
 def test_feasible_fit_monotone_zero_model(self):
  counts=[1]*64;counts[0]=100;counts[42]=70;m=random_start(3,'diffuse',4)
  for delta in [0,.05]:
   for zero in [False,True]:
    r=fit(m,counts,delta,iterations=12,zero=zero);self.assertTrue(r['monotone']);self.assertTrue(feasible(r['model'],delta));self.assertFalse(r['KKT_verified'])
    if zero:self.assertEqual(gross(r['model'])['sum'],0)
 def test_extreme_is_feasible_not_certificate(self):
  m=random_start(3,'asymmetric',7);counts=[1]*64;threshold=loglik(counts,probabilities(m))-10
  r=extreme(m,counts,.05,threshold,'g01',-1,11,{'pattern_steps':[.01],'pattern_sweeps':1,'pattern_proposals_per_sweep':24})
  self.assertTrue(feasible(r['model'],.05));self.assertGreaterEqual(r['loglik'],threshold-1e-7);self.assertLessEqual(r['targets']['g01'],gross(m)['g01']+1e-12);self.assertFalse(r['certified_global_bound'])
if __name__=='__main__':unittest.main()
