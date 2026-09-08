"""监督者独立构造坏输入，核验新增两波适配器的边界。"""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import two_wave as tw

class TwoWaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'sample.csv'
        self.header=['caseid','caseid_22','pid7_20','race_20','hispanic_20','employ_20','ownhome_20','CC20_410','CC20_327a']
        self.row=['synthetic-a','synthetic-b','5','3','1','1','2','1','1']

    def write(self, header=None, rows=None):
        with self.path.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.writer(f);writer.writerow(self.header if header is None else header)
            writer.writerows([self.row] if rows is None else rows)

    def test_field_mapping(self):
        self.write();r=list(tw.read_rows(self.path,'caseid'))[0]
        self.assertEqual(r['id'],'synthetic-a')
        self.assertEqual(r['pid7'],'5');self.assertEqual(r['caseid_22'],'synthetic-b')

    def test_missing_field(self):
        self.write(self.header[:-1],[self.row[:-1]])
        with self.assertRaises(ValueError):list(tw.read_rows(self.path,'caseid'))

    def test_duplicate_header(self):
        self.write(self.header+['caseid'],[self.row+['synthetic-c']])
        with self.assertRaises(ValueError):list(tw.read_rows(self.path,'caseid'))

    def test_short_row(self):
        self.write(rows=[self.row[:-1]])
        with self.assertRaises(ValueError):list(tw.read_rows(self.path,'caseid'))

    def test_long_row(self):
        self.write(rows=[self.row+['extra']])
        with self.assertRaises(ValueError):list(tw.read_rows(self.path,'caseid'))

    def test_original_hash_required(self):
        self.write()
        with self.assertRaises(ValueError):tw.build(self.path,self.path)

    def test_wave_key_duplicate(self):
        with self.assertRaises(ValueError):
            tw.check_wave_ids([{'id':'a','caseid_22':'b'},{'id':'c','caseid_22':'b'}],[])

    def test_wave_key_missing(self):
        for missing in ('','NA','  '):
            with self.assertRaises(ValueError):
                tw.check_wave_ids([{'id':'a','caseid_22':missing}],[])

    def test_wave_key_disagrees(self):
        with self.assertRaises(ValueError):
            tw.check_wave_ids([{'id':'a','caseid_22':'b'}],[{'id':'a','caseid_22':'c'}])

    def test_wave_key_subset(self):
        self.assertIsNone(tw.check_wave_ids([{'id':'a','caseid_22':'b'},{'id':'c','caseid_22':'d'}],[{'id':'a','caseid_22':'b'}]))

    def make_counts(self):
        rows=[dict(id=str(i),pid7='5',race='3',hispanic='1',employ='1',ownhome='2',CC20_410='1',CC20_327a='1') for i in range(100)]
        return tw.build_counts(rows,rows[:80],'published_2022_to_2024_retained')

    def test_conditional_metadata(self):
        r=tw.summarize_counts(self.make_counts())
        self.assertNotIn('two_wave_retention',r)
        self.assertEqual(r['two_wave_retention_status'],'computed')
        s=json.dumps(r,ensure_ascii=False)
        self.assertNotIn('尚未取得',s);self.assertNotIn('年度文件到',s)

    def test_low_n_and_suppression(self):
        r=tw.summarize_counts(self.make_counts())
        allrow=next(x for x in r['rows'] if x['group']=='all' and x['dimension']=='overall')
        self.assertEqual(allrow['inclusion']['value'],0.8)
        self.assertTrue(allrow['selected_composition']['low_n'])
        self.assertIsNone(allrow['not_selected_composition']['value'])
        self.assertEqual(allrow['not_selected_n'],20)

    def test_no_person_ids_in_counts(self):
        text=json.dumps(tw.summarize_counts(self.make_counts()))
        self.assertNotIn('"id"',text);self.assertNotIn('caseid_22',text)

if __name__=='__main__':unittest.main()
