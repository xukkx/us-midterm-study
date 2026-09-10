"""精确小例、标签置换分布与边界验收。"""
import itertools,math,random,unittest
from matched_test import FixedMargins,hg_pmf,tail,synthetic,calculate,make_layers
class MatchedTests(unittest.TestCase):
    def test_exact_label_distribution(self):
        class Rng:
            def __init__(self,x):self.x=x
            def sample(self,pop,k):return self.x
        f=FixedMargins([[1,1],[1,1]]);counts=[0,0,0]
        for x in itertools.permutations(range(4),2):counts[f.draw(Rng(x))[0][0]]+=1
        self.assertEqual(counts,[2,8,2])
    def test_hypergeom_exact(self):
        for n in range(1,13):
            for r in range(n+1):
                for c in range(n+1):
                    for x,p in hg_pmf(n,r,c):self.assertAlmostEqual(p,math.comb(r,x)*math.comb(n-r,c-x)/math.comb(n,c),places=12)
    def test_large_tail_stability(self):
        pmf=hg_pmf(6000,3000,3000);self.assertAlmostEqual(sum(p for x,p in pmf),1);self.assertAlmostEqual(sum(x*p for x,p in pmf),1500,places=7)
    def test_margins(self):
        rng=random.Random(269)
        for _ in range(200):
            t=[[rng.randrange(6) for _ in range(9)] for _ in range(4)];f=FixedMargins(t);d=f.draw(rng)
            self.assertEqual(list(map(sum,d)),f.r);self.assertEqual(list(map(sum,zip(*d))),f.c)
    def test_degenerate(self):
        f=FixedMargins([[0,0,0],[1,0,2]]);self.assertEqual(f.draw(random.Random(1)),f.t);self.assertEqual(f.expectations(),(0,0))
    def test_invalid(self):
        for t in ([],[[]],[[0]],[[True,1]],[[1.5,2]],[[1,-1]],[[1],[1,2]]):
            with self.assertRaises(ValueError):FixedMargins(t)
        with self.assertRaises(ValueError):make_layers([{'H':[9,9],'W':[0,0],'Y':0,'n':1}])
    def test_exact_expected_mi(self):
        f=FixedMargins([[1,1],[1,1]]);self.assertAlmostEqual(f.expected_mi(),math.log(2)/3,places=12)
    def test_seed_and_unknown(self):
        a=calculate(synthetic(),37,269);self.assertEqual(a,calculate(synthetic(),37,269));self.assertEqual(a['n'],20);self.assertGreater(a['unknown_policy_n'],0)
    def test_zero_hits_uncertainty(self):
        t=tail(0,99999);self.assertEqual(t['p_plus_one'],.00001);self.assertGreater(t['MC_Wilson95'][1],0)
if __name__=='__main__':unittest.main()
