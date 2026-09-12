"""合成反例与公共输入契约；不以模型自评分代替检查。"""
import unittest,itertools,math
from recode import recode
from contrast import contrast
class Tests(unittest.TestCase):
    def test_vote_exhaustive(self):
        for t,v in itertools.product([None,-9,-7,-6,-2,0,1], [None,-9,-7,-6,-2,1,2,3,4,5,6]):
            expect='unknown'
            if t==0:expect='conflict' if v in range(1,7) else 'nonvoter'
            elif t==1:expect={1:'D',2:'R',3:'other',4:'other',5:'other',6:'other'}.get(v,'unknown')
            self.assertEqual(recode({'V242095x':t,'V242096x':v})['state'],expect)
    def test_all_feature_combinations(self):
        for e,i,d,r in itertools.product(range(1,6),repeat=4):
            x=recode(dict(zip(['V241451','V242536','V241201','V241206'],[e,i,d,r])))
            self.assertEqual(x['E'],int(e>3));self.assertEqual(x['I'],int(i<3));self.assertEqual(x['C'],'tie' if d==r else 'D_higher' if d<r else 'R_higher')
    def test_negative_retained(self):
        x=recode({'V241451':-8,'V242536':-6});self.assertIsNone(x['E']);self.assertIsNone(x['I']);self.assertEqual(x['reasons']['V242536'],-6)
    def test_contrast_identity(self):
        self.assertAlmostEqual(contrast([[.8,.6,.4,.3],[.4,.1,.7,.2]],[1,3]),-.125)
    def test_invalid_contrasts(self):
        for pp,ww in [([],[]),([[.1]*4],[]),([[.1]*3],[1]),([[.1]*4],[-1]),([[.1]*4],[0]),([[2]*4],[1]),([[math.nan]*4],[1]),([[.1]*4],[math.inf])]:
            with self.assertRaises((ValueError,TypeError)):contrast(pp,ww)
    def test_two_directions(self):
        a=[[.3,.2],[.1,.4]];px=list(map(sum,a));py=[sum(r[j] for r in a) for j in range(2)]
        for i,j in itertools.product(range(2),repeat=2):self.assertAlmostEqual(px[i]*(a[i][j]/px[i]),py[j]*(a[i][j]/py[j]))
    def test_scale_counterexample(self):
        # logit交互为正，概率尺度交互为负：不能只看系数符号。
        p=[.95,.8,.8,.5];pd=p[0]-p[1]-p[2]+p[3];ld=sum(s*math.log(v/(1-v)) for s,v in zip([1,-1,-1,1],p))
        self.assertLess(pd,0);self.assertGreater(ld,0)
if __name__=='__main__':unittest.main()
