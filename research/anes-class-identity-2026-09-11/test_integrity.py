"""检验读模式能发现映射、摘要和输入变化，且不重写被检查文件。"""
import unittest,tempfile,hashlib
from pathlib import Path
from check_package import validate_seal
class Integrity(unittest.TestCase):
    def test_each_tamper_rejected_without_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);names=['input.csv','measurement_manifest.json','report.md'];entries={}
            for n in names:(root/n).write_bytes(b'original');entries[n]=hashlib.sha256(b'original').hexdigest()
            validate_seal(root,entries)
            for n in names:
                (root/n).write_bytes(b'changed')
                with self.assertRaises(AssertionError):validate_seal(root,entries)
                self.assertEqual((root/n).read_bytes(),b'changed');(root/n).write_bytes(b'original')
    def test_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(AssertionError):validate_seal(Path(tmp),{'../escape':'x'})
if __name__=='__main__':unittest.main()
