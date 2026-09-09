"""监督者的穷举、数学恒等式、数值微分与遮蔽反例测试。"""
import itertools,json,math,random,tempfile,unittest
from fractions import Fraction
from pathlib import Path
from bounds_kernel import bound,support
from linear_bounds import optimize
from benchmark import train,metrics,uncertainty
from simulate import generate,simulation_features
import glm

def c(a,b,n=1,w=1):return {'before':a,'after':b,'n':n,'w':w}
class BoundTests(unittest.TestCase):
    def test_all_two_record_completions(self):
        for convention in ('resolved','literal'):
            patterns=list(itertools.product(['D','I','R','not_sure','missing'],repeat=2))
            for a,b in itertools.product(patterns,repeat=2):
                cs=[c(*a),c(*b)];out=bound(cs,convention)
                values=[(v1-u1+v2-u2)/2 for u1,v1,u2,v2 in itertools.product(support(a[0],convention),support(a[1],convention),support(b[0],convention),support(b[1],convention))]
                self.assertEqual((out['lower'],out['upper']),(min(values),max(values)))
                for side in ['lower','upper']:
                    self.assertEqual(sum(x['after_value']-x['before_value'] for x in out[side+'_witness'])/2,out[side])
    def test_negative_coefficients_and_weights(self):
        cs=[c('R','missing',2,5),c('I','R')]
        a=bound(cs,'resolved',True);self.assertAlmostEqual(a['lower'],-4/6);self.assertAlmostEqual(a['upper'],1/6)
        b=bound(cs,'resolved',False,[1,-1]);self.assertEqual((b['lower'],b['upper']),(-3,-1))
        self.assertNotEqual(bound(cs,'resolved')['lower'],a['lower'])
    def test_known_endpoint_resolution_same_target_tightens(self):
        prior=bound([c('R','missing'),c('missing','missing')],'resolved')
        for response in ['D','I','R']:
            new=bound([c('R',response),c('missing','missing')],'resolved')
            self.assertGreaterEqual(new['lower'],prior['lower']);self.assertLessEqual(new['upper'],prior['upper'])
    def test_literal_is_different_target(self):
        self.assertEqual(bound([c('R','not_sure')],'literal')['upper'],-1)
        self.assertEqual(bound([c('R','not_sure')],'resolved')['upper'],0)
    def test_structural_baseline_R(self):
        b=bound([c('R','D',20,20),c('R','I',59,59),c('R','R',663,663),c('R','not_sure',7,7)],'resolved')
        self.assertAlmostEqual(b['lower'],-86/749);self.assertAlmostEqual(b['upper'],-79/749)
    def test_bad_values(self):
        for bad in [c('bad','R'),c('D','R',-1),c('D','R',True),c('D','R',0,1),c('D','R',1,math.nan)]:
            with self.assertRaises(ValueError):bound([bad],'resolved')
        with self.assertRaises(ValueError):bound([c('D','R',1,0)],'resolved',True)
    def test_overlap_joint_not_cartesian(self):
        shared=[c('D','missing')]
        # 两个群体实际上共享同一个未知个案，差值一定0；独立区间相减会错误给[-1,1]。
        result=bound(shared,'resolved',False,[1-1]);self.assertEqual((result['lower'],result['upper']),(0,0))
    def test_lp_enumeration_margins_and_witness(self):
        A=[[1,1,1,1],[1,1,0,0],[1,0,1,0]];b=[5,3,2]
        r=optimize(A,b,[1,0,0,0])
        possibilities=[(a,3-a,2-a,a) for a in range(3)]
        self.assertEqual((r['lower'],r['upper']),(0,2))
        for side in ['lower','upper']:
            x=r[side+'_witness'];self.assertTrue(all(sum(q*z for q,z in zip(row,x))==v for row,v in zip(A,b)))
        t=optimize(A+[[1,0,0,0]],b+[1],[1,0,0,0]);self.assertEqual((t['lower'],t['upper']),(1,1))
        with self.assertRaises(ValueError):optimize(A+[[1,0,0,0]],b+[4],[1,0,0,0])
    def test_incompatible_and_fractional_denominator(self):
        with self.assertRaises(ValueError):optimize([[1,1],[1,1]],[1,2],[1,0])
        r=optimize([[1,1]],[2],[1,0],denominator=[1,2]);self.assertEqual((r['lower'],r['upper']),(0,1))
        with self.assertRaises(ValueError):optimize([[1,1]],[2],[1,0],denominator=[1,0])

class GLMTests(unittest.TestCase):
    def test_gradient_and_hessian_finite_difference(self):
        X=[[1,0],[1,1],[1,-1]];C=[[8,2,5],[4,7,2],[3,4,6]];b=[[.2,-.1],[-.3,.15]]
        loss,g,H=glm.loss_gradient_hessian(b,X,C,1,.05);flat=[v for r in g for v in r];eps=1e-5
        for j in range(4):
            bp=[r[:] for r in b];bm=[r[:] for r in b];bp[j//2][j%2]+=eps;bm[j//2][j%2]-=eps
            lp,gp,_=glm.loss_gradient_hessian(bp,X,C,1,.05);lm,gm,_=glm.loss_gradient_hessian(bm,X,C,1,.05)
            self.assertAlmostEqual(flat[j],(lp-lm)/(2*eps),places=6)
            deriv=[(a-z)/(2*eps) for rp,rm in zip(gp,gm) for a,z in zip(rp,rm)]
            for k in range(4):self.assertAlmostEqual(H[k][j],deriv[k],places=6)
    def test_intercept_and_empty_class(self):
        model=glm.fit([[1],[1]],[[30,10],[10,50]],ridge=1e-7,intercept_ridge=1e-7)
        self.assertTrue(model['converged']);self.assertAlmostEqual(glm.predict(model,[[1]])[0][0],.4,places=7)
        m=glm.fit([[1,0],[1,1]],[[20,0,0],[0,0,20]])
        self.assertTrue(m['converged']);self.assertTrue(all(0<p<1 for row in glm.predict(m,[[1,0],[1,1]]) for p in row))
    def test_reject_weights_as_frequency_and_no_convergence(self):
        with self.assertRaises(ValueError):glm.fit([[1]],[[2.0,3.0]])
        m=glm.fit([[1,0],[1,1]],[[90,10],[2,90]],max_iter=1);self.assertFalse(m['converged'])
        with self.assertRaises(ValueError):glm.predict({'K':2,'p':1,'beta':[[10000]]},[[1]])

class CalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.masked,cls.full=generate('MAR_covariate',random.Random(71),240)
    def test_complete_data_limit(self):
        preds,model=train(self.full,simulation_features);self.assertTrue(model['complete_data_exact'])
        reference=metrics(self.full,'unadjusted')
        for method in ['unadjusted','baseline_standardization','crossfit_aipw']:
            self.assertAlmostEqual(metrics(preds,method)['R_change_pp'],reference['R_change_pp'])
    def test_mask_and_structural_zero(self):
        preds,_=train(self.masked,simulation_features)
        for method in ['unadjusted','baseline_standardization','crossfit_aipw']:
            result=metrics([r for r in preds if r['y0']==2],method)
            self.assertEqual(result['D_to_R_pp'],0);self.assertEqual(result['I_to_R_pp'],0)
        broken=[dict(r) for r in self.masked];next(r for r in broken if not r['s'])['y']=2
        with self.assertRaises(ValueError):train(broken,simulation_features)
    def test_hidden_truth_does_not_change_predictions(self):
        # 真值只在旁表；模型接口不能接收它。改变非法额外结局字段也不进入feature_fn。
        first,_=train(self.masked,simulation_features)
        altered=[dict(r,heldout_2022=0 if not r['s'] else 2) for r in self.masked]
        second,_=train(altered,simulation_features)
        for a,b in zip(first,second):self.assertEqual((a['m'],a['e'],a['phi']),(b['m'],b['e'],b['phi']))
    def test_zero_transition_interval_is_withheld(self):
        rows=[{'key':str(i),'fold':i%5,'s':1,'y0':2,'y':2,'housing':i%2,'latino_employed':0,'age':1,'education':0,'groups':['all']} for i in range(100)]
        preds,_=train(rows,simulation_features)
        for method in ['unadjusted','baseline_standardization','crossfit_aipw']:
            out=uncertainty(preds,method);self.assertFalse(out['valid']);self.assertIsNone(out['ci95_pp'])
    def test_no_observations_fail(self):
        with self.assertRaises(ValueError):train([dict(r,s=0,y=None) for r in self.masked],simulation_features)
if __name__=='__main__':unittest.main()
