"""独立穷举、等价、约束与失败路径测试。"""
import itertools,random,unittest
from algebra import inverse,mm,eye,rank,maxerr,recover_hmm
from models import SEQ,initial,tensor,tensor3,fb,fit_hmm,static_map,static_tensor,latent_summary,fit_static,validate_counts
from experiments import exact,align_error
from probability_kernel import joint
from foundation import budgets,equivalent
class DynamicsTests(unittest.TestCase):
 def test_budget_union_bound(self):
  rng=random.Random(11);m=[(rng.randrange(4),rng.randrange(4),rng.randrange(4),rng.randrange(4)) for _ in range(200)]
  g=sum(a!=b for a,b,c,d in m)/len(m);d=sum((b==2)-(a==2) for a,b,c,d in m)/len(m)
  a0=sum(a!=c for a,b,c,d in m)/len(m);a1=sum(b!=d for a,b,c,d in m)/len(m);bound=budgets(g,d,a0,a1)
  latent_g=sum(c!=d for a,b,c,d in m)/len(m);latent_d=sum((d==2)-(c==2) for a,b,c,d in m)/len(m)
  self.assertTrue(bound['gross'][0]<=latent_g<=bound['gross'][1]);self.assertTrue(bound['R_net'][0]<=latent_d<=bound['R_net'][1])
  with self.assertRaises(ValueError):budgets(.1,0,-.1,.1)
 def test_zero_change_equivalence_and_symmetry(self):
  p=[[.5,.1,0,0],[.02,.18,0,0],[0,0,.2,0],[0,0,0,0]];r=equivalent(p)
  self.assertEqual(r['zero_latent_change']['latent_gross'],0);self.assertLess(r['zero_latent_change']['max_reconstruction_error'],1e-14);self.assertFalse(r['passes_symmetry_necessary_condition'])
  symmetric_indefinite=[[0,.5,0,0],[.5,0,0,0],[0,0,0,0],[0,0,0,0]]
  s=equivalent(symmetric_indefinite);self.assertTrue(s['passes_symmetry_necessary_condition'])
  self.assertNotIn('invariant_zero_change_exactly_compatible',s)
 def test_forward_independent_enumeration(self):
  for k in [2,3,4]:
   m=initial(k,random.Random(k))
   for y in SEQ:
    terms={(i,j,l):m['pi'][i]*m['T01'][i][j]*m['T12'][j][l]*m['E'][i][y[0]]*m['E'][j][y[1]]*m['E'][l][y[2]] for i,j,l in itertools.product(range(k),repeat=3)}
    p=sum(terms.values());actual,q,r=fb(m,y)
    self.assertAlmostEqual(actual,p,places=14);self.assertAlmostEqual(joint(m['pi'],m['T01'],m['T12'],m['E'],y),p,places=14)
    for i,j in itertools.product(range(k),repeat=2):
     self.assertAlmostEqual(q[i][j],sum(terms[i,j,l] for l in range(k))/p,places=13)
     self.assertAlmostEqual(r[i][j],sum(terms[l,i,j] for l in range(k))/p,places=13)
 def test_spectral_exact_distributions(self):self.assertTrue(exact()['passed'])
 def test_inverse_and_rank_failure(self):
  a=[[.8,.2],[.3,.7]];self.assertLess(maxerr(mm(inverse(a),a),eye(2)),1e-14)
  with self.assertRaises(ValueError):inverse([[1,1],[1,1]])
  self.assertEqual(rank([[1,1],[1,1]]),1)
 def test_dynamic_static_equal(self):
  m=initial(4,random.Random(17));self.assertLess(max(abs(a-b) for a,b in zip(tensor(m),static_tensor(static_map(m)))),1e-14)
 def test_counts_reject_signed_weights_empty(self):
  for c in [[0]*64,[-1]+[2]*63,[.5]*64,[True]*64,[1]*63]:
   with self.assertRaises(ValueError):validate_counts(c)
 def test_em_monotonic_and_probability(self):
  counts=[1]*64;counts[0]=100;counts[21]=40;counts[42]=90
  f=fit_hmm(counts,3,9,starts=2,iterations=60)
  self.assertTrue(all(x['likelihood_decreases']==0 for x in f['starts']));self.assertAlmostEqual(sum(tensor(f['model'])),1)
 def test_profile_constraint(self):
  counts=[2]*64;counts[0]=200;counts[42]=100
  for g in [0,.05,.4]:
   f=fit_hmm(counts,3,9,starts=1,iterations=25,gross=g)
   self.assertAlmostEqual(latent_summary(f['model'])['gross01'],g,places=10)
   self.assertTrue(all(x['likelihood_decreases']==0 for x in f['starts']))
 def test_static_can_start_at_hmm(self):
  c=[1]*64;c[0]=80;c[42]=70;h=fit_hmm(c,3,10,starts=1,iterations=30)
  s=fit_static(c,3,10,starts=1,iterations=30,extra=static_map(h['model']))
  self.assertGreaterEqual(s['loglik']+1e-8,h['loglik'])
if __name__=='__main__':unittest.main()
