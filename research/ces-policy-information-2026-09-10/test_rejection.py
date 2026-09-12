"""真实生产结果的篡改负控；所有修改仅发生于隔离临时副本。"""
import json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
class ArtifactRejection(unittest.TestCase):
    def test_changed_statistics_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix='lh269-test-') as tmp:
            dst=Path(tmp)
            for p in HERE.iterdir():
                if p.suffix in ('.py','.json','.csv','.gz'):shutil.copyfile(p,dst/p.name)
            def check(script):return subprocess.run([sys.executable,'-X','utf8','-B',script,'--check'],cwd=dst,capture_output=True).returncode
            self.assertEqual(check('matched_test.py'),0);self.assertEqual(check('support_audit.py'),0)
            p=dst/'matched-test.json';original=p.read_bytes()
            changes=[lambda x:x.update(n=20),lambda x:x['statistics']['MI'].update(hits=1),lambda x:x['statistics']['TV'].update(observed=.5),lambda x:x['statistics']['MI']['null'].update(mean=.9),lambda x:x['layers'][0]['table'][0].__setitem__(0,999)]
            for change in changes:
                x=json.loads(original);change(x);p.write_text(json.dumps(x),encoding='utf-8')
                with self.subTest(change=repr(change)):self.assertNotEqual(check('matched_test.py'),0)
            p.write_bytes(original)
            p=dst/'support-audit.json';original=p.read_bytes();x=json.loads(original);x['summaries']['totalcell_band']['50+']['n_test']-=1;p.write_text(json.dumps(x),encoding='utf-8')
            self.assertNotEqual(check('support_audit.py'),0);p.write_bytes(original)
            p=dst/'support-summary.csv';p.write_bytes(p.read_bytes()+b'bad\n');self.assertNotEqual(check('support_audit.py'),0)
if __name__=='__main__':unittest.main()
