"""合成错误案例及真实匿名格表的结构验收。"""
import csv
import json
import math
import tempfile
import unittest
from pathlib import Path
from transition_summary import summarize
import analyze

def cell(a='D', b='R', n=2, w=4, w2=8, p=2):
    return {'before':a,'after':b,'n':n,'positive_n':p,'w':w,'w2':w2}

class SummaryTests(unittest.TestCase):
    def test_known_numeric_fixture(self):
        r=summarize([cell(),cell('R','D',1,1,1,1),cell('R','R',3,3,3,3)],['D','R'])
        self.assertEqual((r['n'],r['forward_n'],r['reverse_n']),(6,2,1))
        self.assertAlmostEqual(r['unweighted_delta_pp'],100/6)
        self.assertAlmostEqual(r['weighted_delta_pp'],37.5)
        self.assertAlmostEqual(r['n_eff'],64/12)

    def test_independents_in_pid_not_house(self):
        cs=[cell('I','R'),cell('R','I',1,1,1,1)]
        self.assertEqual(summarize(cs,['D','I','R'])['n'],3)
        self.assertEqual(summarize(cs,['D','R'])['n'],0)

    def test_unknown_not_treated_as_exit(self):
        r=summarize([cell('R','unknown')],['D','I','R'])
        self.assertIsNone(r['unweighted_delta_pp'])
        self.assertEqual(r['reverse_n'],0)

    def test_zero_changes_has_no_confidence_interval(self):
        r=summarize([cell('R','R',100,100,100,100)],['D','R'])
        self.assertEqual(r['unweighted_delta_pp'],0)
        self.assertTrue(r['sparse_transitions'])
        self.assertFalse(any('ci' in k or k=='se' for k in r))

    def test_missing_weights_keep_unweighted_denominator(self):
        r=summarize([cell(n=2,w=0,w2=0,p=0)],['D','R'])
        self.assertEqual(r['unweighted_delta_pp'],100)
        self.assertIsNone(r['weighted_delta_pp'])
        self.assertIsNone(r['n_eff'])

    def test_invalid_excluded_cell_rejected(self):
        for key,value in [('n',-1),('n',1.5),('n',True),('positive_n',3),('w',math.nan),('w2',math.inf),('w',-1),('w2',0)]:
            c=cell('unknown','unknown');c[key]=value
            with self.subTest(key=key,value=value),self.assertRaises((ValueError,TypeError)): summarize([c],['D','R'])

    def test_impossible_weight_moments(self):
        for c in [cell(n=1,p=1,w=4,w2=8),cell(w2=40)]:
            with self.assertRaises(ValueError): summarize([c],['D','R'])

class CodingTests(unittest.TestCase):
    def test_groups_stay_fixed(self):
        r={'pid7_20':'5','race_20':'3','hispanic_20':'NA','employ_20':'2','ownhome_20':'2',
           'pid7_22':'1','race_22':'1','employ_22':'4','ownhome_22':'1'}
        self.assertEqual(set(analyze.groups(r)),set(analyze.GROUPS))

    def test_pid_codes(self):
        self.assertEqual([analyze.pid(str(i)) for i in range(1,9)],['D','D','D','I','R','R','R','unknown'])
        self.assertEqual(analyze.pid('NA'),'unknown')
        with self.assertRaises(ValueError): analyze.pid('9')

    def test_party_slot_is_row_specific(self):
        a={'tookpost_20':'2','CC20_412':'1','HouseCand1Party_20':'Republican'}
        b=dict(a,HouseCand1Party_20='Democratic')
        self.assertEqual((analyze.house(a,20),analyze.house(b,20)),('R','D'))
        self.assertEqual(analyze.house({'tookpost_20':'2','CC20_412':'9','HouseCand9Party':'Democratic'},20),'D')

    def test_nonvote_is_not_survey_missing(self):
        r={'tookpost_22':'2','CC22_412':'12'}
        self.assertEqual(analyze.house(r,22),'not_vote')
        self.assertEqual(analyze.house(dict(r,tookpost_22='1'),22),'not_post')
        self.assertEqual(analyze.house(dict(r,CC22_412='NA'),22),'missing_item')
        with self.assertRaises(ValueError): analyze.house(dict(r,CC22_412='9'),22)

    def test_weight_errors(self):
        self.assertIsNone(analyze.weight('NA'));self.assertEqual(analyze.weight('0'),0)
        for s in ['nan','inf','-1']:
            # NAN在本数据约定中是缺失；无穷和负数才是非法权重。
            if s=='nan': self.assertIsNone(analyze.weight(s))
            else:
                with self.assertRaises(ValueError): analyze.weight(s)

    def test_bad_headers_rows_and_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.csv'
            for text in ['a,a\n1,2\n','a,b\n1\n','b\n1\n']:
                p.write_text(text,encoding='utf-8')
                with self.assertRaises(ValueError): list(analyze.projected_rows(p,['a']))
            cols=['caseid','caseid_22',*analyze.BASELINE]
            with p.open('w',encoding='utf-8',newline='') as f:
                w=csv.writer(f);w.writerow(cols);w.writerow(['1','2',*['1']*7]);w.writerow(['1','3',*['1']*7])
            with self.assertRaises(ValueError): analyze.member_map(p,'caseid')

class ReleasedCellsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((Path(__file__).parent/'cells.json').read_bytes())
        cls.result=analyze.compute(cls.data)

    def test_partition_every_transition(self):
        indexed={(c['group'],c['measure'],c['cohort'],c['before'],c['after']):c for c in self.data['cells']}
        for c in self.data['cells']:
            if c['cohort']!='full': continue
            members=[indexed.get((c['group'],c['measure'],s,c['before'],c['after']),{}) for s in ['retained','omitted']]
            for k in ['n','positive_n','weight_missing_n','weight_zero_n']:
                self.assertEqual(c[k],sum(x.get(k,0) for x in members))
            for k in ['w','w2']: self.assertAlmostEqual(c[k],sum(x.get(k,0) for x in members),places=7)

    def test_denominators_and_mixture_identity(self):
        for g in analyze.GROUPS:
            for m in analyze.WEIGHTS:
                rs={x['cohort']:x['estimate'] for x in self.result['rows'] if x['group']==g and x['measure']==m}
                a,b,f=rs['retained'],rs['omitted'],rs['full']
                self.assertEqual(f['n'],a['n']+b['n'])
                self.assertAlmostEqual(f['unweighted_delta_pp'],(a['n']*a['unweighted_delta_pp']+b['n']*b['unweighted_delta_pp'])/f['n'])
                self.assertAlmostEqual(f['weighted_delta_pp'],(a['w']*a['weighted_delta_pp']+b['w']*b['weighted_delta_pp'])/f['w'])
                for e in rs.values(): self.assertLessEqual(e['n_eff'],e['positive_n']+1e-8)

    def test_no_2024_outcomes_or_weights(self):
        self.assertEqual({c['measure'] for c in self.data['cells']},{'pid','house'})
        self.assertEqual(set(analyze.WEIGHTS.values()),{'commonweight_22','commonpostweight_22'})
        self.assertEqual(self.data['totals']['all'],{'full':11009,'retained':6175,'omitted':4834})

if __name__=='__main__': unittest.main()
