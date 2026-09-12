"""LH263.1评审反例：区间目标与匿名组合完整性。"""
import copy,json,unittest
from pathlib import Path
from benchmark import uncertainty,metrics
from anonymous_benchmark import check

def fixture():
    rows=[]
    for group,remain in [('A',40),('B',10)]:
        for i in range(100):
            s=int(i<50);y=2 if i<remain else 0
            p=[.5,0,.5];phi=[p[k]+2*(int(y==k)-p[k]) if s else p[k] for k in range(3)]
            rows.append({'key':group+str(i),'group':group,'y0':2,'y':y if s else None,'s':s,'std':p,'std_phi':phi,'phi':phi})
    return rows

class MaintenanceTests(unittest.TestCase):
    def test_reviewer_cutting_subgroup_is_rejected(self):
        full=fixture();sub=[r for r in full if r['group']=='A']
        self.assertAlmostEqual(metrics(sub,'baseline_standardization')['R_change_pp'],-50)
        out=uncertainty(sub,'baseline_standardization',fitting_population=full)
        self.assertFalse(out['valid']);self.assertEqual(out['state'],'unsupported_standardization_subgroup');self.assertIsNone(out['ci95_pp'])
    def test_explicit_full_population_has_correct_center(self):
        full=fixture();out=uncertainty(full,'baseline_standardization',fitting_population=full)
        self.assertTrue(out['valid']);self.assertAlmostEqual(sum(out['ci95_pp'])/2,-50)
    def test_whole_cell_subgroup_also_explicitly_unsupported(self):
        first=fixture();second=[dict(r,key='other'+r['key'],y0=0) for r in fixture()]
        full=first+second
        self.assertEqual(uncertainty(first,'baseline_standardization',fitting_population=full)['state'],'unsupported_standardization_subgroup')
    def test_context_required_and_baseline_R_no_increase(self):
        full=fixture();self.assertFalse(uncertainty(full,'baseline_standardization')['valid'])
        self.assertLessEqual(metrics(full,'baseline_standardization')['R_change_pp'],0)
    def test_zero_transition_has_no_interval(self):
        full=[dict(r,y=2 if r['s'] else None,std=[0,0,1],std_phi=[0,0,1]) for r in fixture()]
        self.assertIsNone(uncertainty(full,'baseline_standardization',fitting_population=full)['ci95_pp'])
    def test_anonymous_complete_and_reordering(self):
        here=Path(__file__).parent;a=json.loads((here/'benchmark-sufficient.json').read_bytes());b=json.loads((here/'benchmark-results.json').read_bytes())
        self.assertEqual(check(a,b),36);b['rows'].reverse();self.assertEqual(check(a,b),36)
    def test_empty_unequal_missing_duplicate_unexpected(self):
        here=Path(__file__).parent;a=json.loads((here/'benchmark-sufficient.json').read_bytes());b=json.loads((here/'benchmark-results.json').read_bytes())
        pairs=[({'rows':[]},{'rows':[]}),({'rows':a['rows'][:-1]},b),(a,{'rows':b['rows'][:-1]}),(a,{'rows':b['rows']+[b['rows'][0]]})]
        dup=copy.deepcopy(a);dup['rows'][-1]=dup['rows'][0];pairs.append((dup,b))
        extra=copy.deepcopy(b);extra['rows'][-1]['group']='unexpected';pairs.append((a,extra))
        for x,y in pairs:
            with self.subTest(rows=(len(x['rows']),len(y['rows']))):
                with self.assertRaises(ValueError):check(x,y)
if __name__=='__main__':unittest.main()
