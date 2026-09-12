"""输入边界、固定边际、离散参考与保守区间的实质测试。"""
import itertools,math,random,unittest
from likelihood import loglik
from reference import FixedMargins,cp_interval,holm,hypergeom_cdf,tail_result
from hypergeom_kernel import hypergeom_pmf
from policy_calibration import strata,r1_calibrate,r2_calibrate
from history_nested import fit,score
class CalibrationTests(unittest.TestCase):
 def test_dimensions_and_zero_support(self):
  with self.assertRaises(ValueError):loglik([1]*64,[1.])
  with self.assertRaises(ValueError):loglik([1]+[0]*63,[0,1]+[0]*62)
  self.assertEqual(loglik([3]+[0]*63,[1]+[0]*63),0.)
 def test_counts_and_invalid_probability(self):
  for counts in [[0]*64,[1.]*64,[-1]+[1]*63,[True]*64]:
   with self.assertRaises(ValueError):loglik(counts,[1/64]*64)
  for p in [[math.nan]+[1/64]*63,[math.inf]+[0]*63,[-.1,1.1]+[0]*62,[True]+[0]*63]:
   with self.assertRaises(ValueError):loglik([1]*64,p)
  self.assertAlmostEqual(loglik([1]*64,[1/64]*64),-64*math.log(64))
 def test_subnormal_no_floor(self):
  self.assertAlmostEqual(loglik([1]+[0]*63,[1e-320,1.]+[0]*62),math.log(1e-320))
 def test_hypergeom_exhaustive(self):
  for N in range(8):
   for K in range(N+1):
    for n in range(N+1):
     choices=list(itertools.combinations(range(N),n));pmf=dict(hypergeom_pmf(N,K,n))
     for x,p in pmf.items():self.assertAlmostEqual(p,sum(sum(i<K for i in c)==x for c in choices)/len(choices))
 def test_margins_and_zero_rows(self):
  for table in [[[0,0],[2,3],[0,0]],[[1,2,0],[3,0,0],[0,1,0]],[[0,0],[0,0],[0,0]]]:
   ref=FixedMargins(table);rng=random.Random(9)
   for _ in range(50):
    t=ref.draw(rng);self.assertEqual([sum(r) for r in t],ref.rows);self.assertEqual([sum(r[j] for r in t) for j in range(len(t[0]))],ref.cols)
 def test_uniform_assignments_two_by_two(self):
  r=FixedMargins([[1,1],[1,1]]);rng=random.Random(30);n=12000;freq=[0]*3
  for _ in range(n):freq[r.draw(rng)[0][0]]+=1
  for x,p in hypergeom_pmf(4,2,2):self.assertLess(abs(freq[x]/n-p),.025)
 def test_cp_exact_boundary_and_coverage(self):
  self.assertEqual(cp_interval(0,0),(0,1));self.assertAlmostEqual(cp_interval(0,10)[1],1-.025**.1)
  for p in [.01,.1,.3,.5,.9,.99]:
   coverage=sum(math.comb(10,k)*p**k*(1-p)**(10-k) for k in range(11) if cp_interval(k,10)[0]<=p<=cp_interval(k,10)[1]);self.assertGreaterEqual(coverage,.95-1e-12)
 def test_holm_plus_one(self):
  self.assertEqual(holm([.04,.01,.2]),[.08,.03,.2]);self.assertEqual(tail_result(0,99)['p_plus_one'],.01);self.assertGreater(tail_result(0,99)['MC_Wilson95'][1],0)
 def test_policy_pair_kept(self):
  j=[[0]*27 for _ in range(64)];j[0][9+6+1]=3;j[4][9+6+1]=2;j[0][9+6]=4
  s=strata(j);self.assertEqual(len(s),1);self.assertEqual(s[0]['table'],[[0,0,3,0],[0,0,2,0],[0,0,0,0]])
  r=r1_calibrate(s,29,1);self.assertAlmostEqual(r['statistics']['MI']['observed'],0.);self.assertEqual(r['statistics']['MI']['p_plus_one'],1.)
 def test_r2_average_not_stratum_certificate(self):
  rows=[{'baseline_PID':0,'baseline_policy':1,'table':[[8,0,2,0],[1,0,3,0],[0]*4]},{'baseline_PID':1,'baseline_policy':1,'table':[[8,0,2,0],[4,0,0,0],[0]*4]}]
  r=r2_calibrate(rows,39,3,4);self.assertGreater(r['observed_average_difference'],0);self.assertFalse(r['all_supported_strata_nonnegative_lower_bound'])
 def test_history_parent_fallback_and_nested_count(self):
  raw=[0]*512;raw[8*3+6]=10;p,q=fit(raw)
  for a in [1,2,3]:
   for x,y in zip(q[a][3],p[3]):self.assertAlmostEqual(x,y)
  self.assertAlmostEqual(q[0][3][2],(10+20*10.25/11)/30)
 def test_history_calibration_and_contribution(self):
  raw=[0]*512;raw[0]=4;raw[64*1+8*3+6]=2;p,q=fit(raw);s=score(raw,p,q)
  self.assertEqual(s['n'],6);self.assertEqual(sum(x['n'] for x in s['path_contributions'].values()),6)
  self.assertAlmostEqual(sum(x['logscore_difference_sum'] for x in s['path_contributions'].values()),s['logscore_sum'][1]-s['logscore_sum'][0])
  self.assertTrue(all(sum(x['n'] for x in rows)==6 for model in s['calibration'] for rows in model))
if __name__=='__main__':unittest.main()
