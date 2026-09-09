"""四态一致性、遮蔽、结构等价与DR恒等式的独立小例。"""
import copy,math,random,unittest
from engine import train,sufficient,summarize,METHODS
from analyze import summarize_benchmark
from latent_kernel import reconstruct
from structure import boundary
from dr_simulation import oracle_identity,estimate_interval

def population():
    out=[]
    for i in range(240):
        s=int(i%3!=0);y=(i//4)%4
        out.append({'key':str(i),'fold':i%5,'s':s,'y0':i%4,'y':y if s else None,'housing':(i//2)%2,'latino_employed':int(i%7==0),'age':i%3,'education':i%2})
    return out
class FourStateTests(unittest.TestCase):
    def test_complete_four_state_and_NS_paths(self):
        rows=[dict(r,s=1,y=(i//4)%4) for i,r in enumerate(population())];p,m=train(rows)
        for method in METHODS:
            s=summarize(sufficient(p,method));self.assertEqual(len(s['flows_pp']),12);self.assertGreater(s['flows_pp']['3_to_2'],0);self.assertGreater(s['flows_pp']['2_to_3'],0)
        self.assertTrue(m['complete_data_exact'])
    def test_four_state_mask_and_nuisance(self):
        rows=population();pred,m=train(rows);altered=[dict(r,forbidden_y22=3) for r in rows];second,_=train(altered)
        self.assertEqual(len(pred),240);self.assertEqual(m['K'],4)
        for a,b in zip(pred,second):
            self.assertEqual((a['m'],a['e'],a['phi']),(b['m'],b['e'],b['phi']));self.assertEqual(len(a['phi']),4);self.assertAlmostEqual(sum(a['phi']),1)
        broken=copy.deepcopy(rows);next(r for r in broken if not r['s'])['y']=3
        with self.assertRaises(ValueError):train(broken)
    def test_baseline_R_structural_rows_zero(self):
        pred,_=train(population());sub=[r for r in pred if r['y0']==2]
        for method in METHODS:
            s=summarize(sufficient(sub,method));self.assertTrue(all(v==0 for i,row in enumerate(s['matrix']) if i!=2 for v in row))
    def test_anonymous_empty_rejected(self):
        for x in ({'rows':[]},{'rows':[{}]*9},{'rows':None}):
            with self.assertRaises(ValueError):summarize_benchmark(x)
    def test_matrix_margins_rejected(self):
        with self.assertRaises(ValueError):summarize({'n':2,'baseline_counts':[1,1,0,0],'matrix_totals':[[0]*4 for _ in range(4)]})
class StructuralTests(unittest.TestCase):
    def test_known_emissions_recover_Q(self):
        Q=[[.22 if i==j else .01 for j in range(4)] for i in range(4)];e=.1
        E=[[.9*int(i==j)+.025 for j in range(4)] for i in range(4)]
        # 独立四重求和生成观测；不导入生产矩阵乘法。
        P=[[sum(E[a][i]*Q[a][b]*E[b][j] for a in range(4) for b in range(4)) for j in range(4)] for i in range(4)]
        observed=reconstruct(P,0,0);latent=reconstruct(P,e,e)
        self.assertTrue(latent['feasible']);self.assertGreater(abs(observed['gross_change']-latent['gross_change']),.05)
        for i in range(4):
            for j in range(4):self.assertAlmostEqual(latent['Q'][i][j],Q[i][j],places=12)
        self.assertLess(latent['max_error'],1e-12)
    def test_boundary_vs_dense_grid_and_negative_preserved(self):
        rng=random.Random(264)
        for _ in range(30):
            v=[rng.random() for _ in range(16)];T=sum(v);P=[[v[4*i+j]/T for j in range(4)] for i in range(4)]
            for family in ('late_only','invariant'):
                limit=boundary(P,family)
                for e in [0,limit/2,limit]:self.assertTrue(reconstruct(P,e if family=='invariant' else 0,e)['feasible'])
                if limit<.19999:
                    e=limit+1e-5;r=reconstruct(P,e if family=='invariant' else 0,e)
                    self.assertFalse(r['feasible']);self.assertLess(min(x for row in r['Q'] for x in row),0)
    def test_structural_invalid_inputs(self):
        P=[[.0625]*4 for _ in range(4)]
        for e in (1,-.1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):reconstruct(P,0,e)
        with self.assertRaises(ValueError):reconstruct(P[:3],0,0)
class DRTests(unittest.TestCase):
    def test_exact_two_single_correct_cases(self):
        for row in oracle_identity():
            if row['correct_nuisance']!='neither':self.assertAlmostEqual(row['exact_expected_bias_pp'],0,places=12)
            else:self.assertGreater(abs(row['exact_expected_bias_pp']),.01)
    def test_no_std_subgroup_interval(self):
        full=[{'key':str(i),'y0':i%2,'y':1-i%2,'s':1,'std':[.5,.5],'std_phi':[.5,.5],'phi':[.5,.5]} for i in range(40)]
        self.assertEqual(estimate_interval(full[:20],'baseline_standardization',full)['state'],'unsupported_standardization_subgroup')
if __name__=='__main__':unittest.main()
