"""分母、折外预测与聚合限制的独立小例验收。"""
import unittest
from history import fit,lumpability,MAP
from policy import summarize
from project import policy_code,path_group
class ObservedTests(unittest.TestCase):
 def test_empty_history_backs_off(self):
  p=fit([0]*64,[0]*512)
  self.assertEqual(p['first'],[[.25]*4 for _ in range(4)])
  self.assertTrue(all(abs(v-.25)<1e-14 for row in p['raw'] for v in row))
  self.assertEqual(p['history'][0],p['first'])
 def test_no_training_history_uses_first(self):
  c=[0]*64;c[16*0+4*1+2]=10;p=fit(c,[0]*512)
  for x,y in zip(p['history'][3][1],p['first'][1]):self.assertAlmostEqual(x,y)
  self.assertAlmostEqual(p['history'][0][1][2],(10+20*10.25/11)/30)
 def test_lumpability(self):
  rows=[[.2,.3,.5],[.4,.1,.5],[.1,.1,.8]]
  self.assertEqual(lumpability(rows,[0,0,1]),{'0':0.,'1':0.})
  rows[1]=[.2,.1,.7];self.assertAlmostEqual(lumpability(rows,[0,0,1])['0'],.2)
  self.assertEqual([i+1 for i,x in enumerate(MAP) if x==1],[4])
 def test_missing_triple_and_pair_denominators(self):
  j=[[0]*27 for _ in range(64)];j[0][1*9+2*3+1]=3;j[0][1*9+2*3]=2
  row=summarize(j)['path_rows'][0]
  self.assertEqual((row['retained_n'],row['policy_complete_n'],row['missing_any_n']),(5,3,2))
  self.assertEqual(row['policy_return_n'],3)
  self.assertEqual(row['intervals']['0']['oppose_to_support_n'],3)
  self.assertEqual(row['intervals']['0']['pair_oppose_to_support_n'],5)
  self.assertEqual(row['intervals']['1']['pair_known_denominator'],3)
 def test_coding_and_exhaustive_paths(self):
  self.assertEqual([policy_code(x) for x in ['NA','1','2']],[0,2,1])
  with self.assertRaises(ValueError):policy_code('3')
  self.assertEqual([path_group(x) for x in [(0,0,0),(0,1,0),(0,0,1),(0,1,1)]],['stable','return','nonreturn_change','nonreturn_change'])
if __name__=='__main__':unittest.main()
