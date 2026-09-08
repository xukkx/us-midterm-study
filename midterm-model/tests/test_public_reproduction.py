"""公开实证表的独立锚点及失败路径。"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'public'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
r=module('reproduce');a=module('audit_annual')

class 公开复现测试(unittest.TestCase):
    def test_对称分解独立手算与方向翻转(self):
        # 两组：比例(0.4,0.6)->(0.5,0.5)，组均值(0.2,0.4)->(0.3,0.5)。
        got=r.symmetric_components(-.02,.10,0.)
        self.assertAlmostEqual(got['composition'],-.02)
        self.assertAlmostEqual(got['within_group'],.10)
        self.assertAlmostEqual(sum(got.values()),.40-.32)
    def test_全部已匹配但没有投票方法不视为投票(self):
        row={'pid7':'5','ownhome':'2','TS_voterstatus':'1','TS_g2024':'7'}
        self.assertEqual(a.classify(2024,row),(True,'rent',True,False))
    def test_unknown是投票方法未知而非没有投票记录(self):
        row={'pid7':'5.0','ownhome':'2.0','CL_matched':'Y','CL_E2016GVM':'unknown'}
        self.assertEqual(a.classify(2016,row),(True,'rent',True,True))
    def test_未匹配保持独立状态(self):
        row={'pid7':'7','ownhome':'2','TS_voterstatus':'NA','TS_g2024':'NA'}
        self.assertEqual(a.classify(2024,row),(True,'rent',False,False))
        row['TS_g2024']='6'
        with self.assertRaises(ValueError):a.classify(2024,row)
    def test_非法编码权重拒绝(self):
        with self.assertRaises(ValueError):a.number('nan')
        with self.assertRaises(ValueError):a.number('-1')
        with self.assertRaises(ValueError):a.classify(2024,{'pid7':'7','ownhome':'2','TS_voterstatus':'99','TS_g2024':'NA'})
    def test_生产表行数与独立锚点(self):
        rep=r.build()
        self.assertEqual(len(rep['ecological_profile']),32)
        self.assertEqual(len(rep['renter_turnout_audit']),16)
        self.assertEqual(len(rep['annual_match_audit']),10)
        self.assertAlmostEqual(rep['house_sensitivity']['environment_contribution_difference_pp'],4.3392684)
        row=next(x for x in rep['annual_match_audit'] if x['year']==2024 and x['tenure']=='rent')
        self.assertEqual(row['sample_n'],5706)
        self.assertEqual(row['matched_n'],3028)
        self.assertAlmostEqual(row['recorded_vote_rate'],row['weighted_match_rate']*row['matched_only_rate'])
        self.assertTrue(.40<row['weighted_match_rate']<.41)
        self.assertTrue(.89<row['matched_only_rate']<.90)
    def test_输入遭改动即失败(self):
        original=r.HERE
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'inputs';p.mkdir()
            for f in (original/'inputs').iterdir():
                if f.is_file():(p/f.name).write_bytes(f.read_bytes())
            (p/'county-input.csv').write_bytes((p/'county-input.csv').read_bytes()+b'\n')
            try:
                r.HERE=Path(d)
                with self.assertRaises((ValueError,AssertionError)):r.build()
            finally:r.HERE=original

if __name__=='__main__':unittest.main()
