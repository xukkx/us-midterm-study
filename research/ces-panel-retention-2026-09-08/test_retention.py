"""监督者独立合成样例；测试关键连接、缺失、闭合和阈值。"""
import copy
import unittest
from retention_core import build_counts
from summarize import summarize,rate

def row(key,**kwargs):
    r={'id':str(key),'pid7':'2','race':'1','hispanic':'2','employ':'1','ownhome':'1','CC20_410':'1','CC20_327a':'1'}
    r.update(kwargs);return r

class RetentionTests(unittest.TestCase):
    def test_exact_counts_and_groups(self):
        a=row(1,race='3');b=row(2,pid7='6',ownhome='2');c=row(3,hispanic='1',employ='2')
        out=build_counts([a,b,c],[a,b],'synthetic')
        d={(r['group'],r['dimension'],r['category']):r for r in out['rows']}
        self.assertEqual((out['totals']['baseline_n'],out['totals']['selected_n']), (3,2))
        self.assertEqual(d[('Latino_employed_2020','overall','all')]['baseline_n'],2)
        self.assertEqual(d[('Latino_employed_2020','overall','all')]['selected_n'],1)
        self.assertEqual(d[('R_renter_2020','overall','all')]['selected_n'],1)
        summarize(out)

    def test_duplicate_baseline(self):
        with self.assertRaises(ValueError):build_counts([row(1),row(1)],[],'synthetic')
    def test_duplicate_selected(self):
        with self.assertRaises(ValueError):build_counts([row(1)],[row(1),row(1)],'synthetic')
    def test_missing_id(self):
        for v in (None,'','NA'):
            with self.subTest(v=v),self.assertRaises(ValueError):build_counts([row(1,id=v)],[],'synthetic')
    def test_selected_outside_frame(self):
        with self.assertRaises(ValueError):build_counts([row(1)],[row(2)],'synthetic')
    def test_each_baseline_field_must_match(self):
        for field,value in [('pid7','5'),('race','3'),('hispanic','1'),('employ','2'),('ownhome','2'),('CC20_410','2'),('CC20_327a','2')]:
            with self.subTest(field=field),self.assertRaises(ValueError):build_counts([row(1)],[row(1,**{field:value})],'synthetic')
    def test_missing_is_not_zero_or_other(self):
        r=row(1,pid7='NA',employ='NA',ownhome='NA',race='NA',hispanic='NA')
        out=build_counts([r],[r],'synthetic');d={(x['group'],x['dimension'],x['category']):x for x in out['rows']}
        self.assertEqual(d[('all','pid','unknown')]['baseline_n'],1)
        self.assertEqual(d[('all','employment','other')]['baseline_n'],0)
        self.assertEqual(d[('all','tenure','unknown')]['selected_n'],1)
    def test_illegal_categories_fail(self):
        for k,v in [('pid7','9'),('race','0'),('hispanic','3'),('employ','10'),('ownhome','4')]:
            with self.subTest(k=k),self.assertRaises(ValueError):build_counts([row(1,**{k:v})],[],'synthetic')
    def test_missing_column_not_silently_unknown(self):
        r=row(1);del r['hispanic']
        with self.assertRaises(ValueError):build_counts([r],[],'synthetic')
    def test_unregistered_missing_marker_is_illegal(self):
        with self.assertRaises(ValueError):build_counts([row(1,pid7='NULL')],[],'synthetic')
    def test_numeric_coding_normalization(self):
        out=build_counts([row(1)],[row(1,pid7='2.0')],'synthetic')
        self.assertEqual(out['totals']['selected_n'],1)
    def test_employment_is_required_for_worker_group(self):
        out=build_counts([row(1,race='3',employ='5')],[],'synthetic')
        r=next(x for x in out['rows'] if x['group']=='Latino_employed_2020' and x['dimension']=='overall')
        self.assertEqual(r['baseline_n'],0)
    def test_threshold_boundaries(self):
        self.assertIsNone(rate(1,79)['value']);self.assertTrue(rate(1,80)['low_n'])
        self.assertTrue(rate(1,99)['low_n']);self.assertFalse(rate(1,100)['low_n'])
        self.assertEqual(rate(40,80)['value'],.5)
    def test_no_id_in_output(self):
        import json
        result=build_counts([row('synthetic-person-unique')],[],'synthetic')
        self.assertNotIn('synthetic-person-unique',json.dumps(result))
    def test_missing_zero_cell_is_rejected(self):
        out=build_counts([row(1)],[],'synthetic');out['rows'].pop()
        with self.assertRaises(ValueError):summarize(out)
    def test_unclosed_counts_rejected(self):
        out=build_counts([row(1)],[],'synthetic');out['rows'][0]['not_selected_n']+=1
        with self.assertRaises(ValueError):summarize(out)
    def test_duplicate_aggregate_rejected(self):
        out=build_counts([row(1)],[],'synthetic');out['rows'].append(copy.deepcopy(out['rows'][0]))
        with self.assertRaises(ValueError):summarize(out)

if __name__=='__main__':unittest.main()
