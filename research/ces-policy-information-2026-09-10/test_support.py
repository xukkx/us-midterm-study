import json,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from support_audit import band,score,shrink,support_audit_rows,verify_result
class TestSupport(unittest.TestCase):
 def test_bands(self): self.assertEqual([band(x) for x in (0,1,4,5,19,20,49,50)],['0-0','1-4','1-4','5-19','5-19','20-49','20-49','50+'])
 def test_score_closure(self):
  s=score([.2,.3,.4,.1],2,0); self.assertAlmostEqual(s['full_log'],s['event_log']+s['dest_log'])
  self.assertAlmostEqual(score([.7,.1,.1,.1],0,0)['binary_brier'],(.3)**2)
 def test_shrink(self): self.assertEqual(shrink([1,2,0,1],[.25]*4),[6/24,7/24,5/24,6/24])
 def test_audit_and_tamper(self):
  rows=[{'PID20raw':1,'PID22raw':1,'PID24raw':1,'policy20':0,'policy22':1,'n':5,'fold_counts':[5,0,0,0,0]}]
  child=[[[.7,.1,.1,.1] for _ in range(8)] for _ in range(4)]; base=[child for _ in range(5)]
  ch={'folds':[{'training_cells':{'0|1|0|1':{'training_target_counts':[0,0,0,0],'n_train':0,'baseline_q':[.7,.1,.1,.1],'q_new':[.7,.1,.1,.1]}}} for _ in range(5)]}
  out=support_audit_rows(rows,ch); self.assertEqual(sum(x['n_test'] for x in out),5); self.assertEqual(out[0]['target_n'],0)
  with self.assertRaises(ValueError): support_audit_rows([{**rows[0],'n':6}], ch)
 def test_negative_controls(self):
  import support_audit
  expected,_,_=support_audit.build_result(); altered=json.loads(json.dumps(expected)); altered['totals']['loss_delta_sum']['full_log']+=1
  with self.assertRaises(AssertionError): verify_result(altered,expected)
  with self.assertRaises(ValueError): support_audit.probs([.5,.5,.0])
if __name__=='__main__': unittest.main()
