"""独立预期、穷举与篡改负控；不以生产内核自证。"""
import copy
import itertools
import json
import math
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from accounting_kernel import account
import build

HERE=Path(__file__).resolve().parent
LABELS=('D','R','O','A','N','U')
SIGN={'D':-1,'R':1,'O':0,'A':0,'N':0}
CATS=('repeat_vote_choice','election_entry','election_exit','contest_entry','contest_exit','other_zero')

def grid(people):
    g={(a,b):dict(before=a,after=b,n=0,adult_w=0,post_w=0,post_n=0) for a in LABELS for b in LABELS}
    for a,b,w,p in people:
        r=g[a,b];r['n']+=1;r['adult_w']+=w
        if p is not None:r['post_w']+=p;r['post_n']+=1
    return list(g.values())

def cat(a,b):
    key=('vote' if a in ('D','R','O') else a,'vote' if b in ('D','R','O') else b)
    return {('vote','vote'):CATS[0],('N','vote'):CATS[1],('vote','N'):CATS[2],('A','vote'):CATS[3],('vote','A'):CATS[4]}.get(key,CATS[5])

def brute(people,weight_index=2):
    possibilities=[]
    for p in people:
        a,b=p[:2];w=1 if weight_index is None else p[weight_index]
        if w is None:continue
        poss=[]
        for x,y in itertools.product(SIGN if a=='U' else (a,),SIGN if b=='U' else (b,)):
            vals={k:0 for k in CATS};vals[cat(x,y)]=w*(SIGN[y]-SIGN[x]);poss.append(vals)
        possibilities.append(poss)
    vals=[]
    for sample in itertools.product(*possibilities):
        parts={k:sum(v[k] for v in sample) for k in CATS};parts['total']=sum(parts.values());vals.append(parts)
    return {k:[min(v[k] for v in vals),max(v[k] for v in vals)] for k in (*CATS,'total')}

class KernelTests(unittest.TestCase):
    def test_eight_fixed_checks(self):
        self.assertEqual(237+137+40,414);self.assertEqual(7221+768+3020,11009)
        people=[('D','R',2,2),('R','R',1,None)]
        out=account(grid(people))['modes'];self.assertEqual(len(out['adult']['grid']),36)
        self.assertEqual(out['adult']['known_delta'],4);self.assertEqual(out['post']['missing_weight_n'],1)
        self.assertEqual(out['post']['weight_sum'],2)
        self.assertEqual(account(grid([('D','U',1,1),('U','R',1,1)]))['modes']['unweighted']['delta_bounds'],[0,4])
        with self.assertRaises(json.JSONDecodeError):json.loads('{"answer":4')

    def test_signed_examples(self):
        for pair,expected in [(('D','R'),2),(('N','R'),1),(('D','N'),1),(('O','N'),0)]:
            self.assertEqual(account(grid([(*pair,1,1)]))['modes']['unweighted']['known_delta'],expected)

    def test_all_36_pairs_independent(self):
        for a,b in itertools.product(LABELS,repeat=2):
            people=[(a,b,2.5,None)];expected=brute(people)
            actual=account(grid(people))['modes']['adult']
            self.assertEqual(actual['delta_bounds'],expected['total'])
            for k in CATS:self.assertEqual(actual['components'][k]['bounds'],expected[k])

    def test_three_person_joint_enumeration(self):
        people=[('U','U',0.5,2),('D','U',2,None),('U','R',3,1)]
        out=account(grid(people))['modes']
        for mode,i in [('unweighted',None),('adult',2),('post',3)]:
            expected=brute(people,i);self.assertEqual(out[mode]['delta_bounds'],expected['total'])
            for k in CATS:self.assertEqual(out[mode]['components'][k]['bounds'],expected[k])

    def test_components_not_joint_extremes(self):
        x=account(grid([('U','U',1,1)]))['modes']['unweighted']
        self.assertLess(x['delta_bounds'][1],sum(z['bounds'][1] for z in x['components'].values()))

    def test_known_conservation_and_fixed_weights(self):
        rnd=random.Random(304)
        for _ in range(50):
            ps=[(rnd.choice(tuple(SIGN)),rnd.choice(tuple(SIGN)),rnd.choice([0.5,1,2]),1) for i in range(20)]
            x=account(grid(ps))['modes']['adult']
            expected=sum(w*(SIGN[b]-SIGN[a]) for a,b,w,_ in ps)
            self.assertEqual(x['known_delta'],expected)
            self.assertEqual(x['after_bounds'][0]-x['before_bounds'][0],expected)
            self.assertEqual(sum(z['known_delta'] for z in x['components'].values()),expected)

    def test_empty_denominator_is_null(self):
        x=account(grid([]))['modes']['post'];self.assertIsNone(x['per100_bounds']);self.assertIsNone(x['known_delta_per100'])

    def test_missing_zero_weight_coverage(self):
        x=account(grid([('D','R',1,None),('D','R',1,0)]))['modes']['post']
        self.assertEqual((x['covered_n'],x['missing_weight_n'],x['weight_sum']),(1,1,0))

    def test_bad_grids_fail(self):
        g=grid([])
        bads=[g[:-1],g+[g[0]],g[:-1]+[g[0]]]
        for key,val in [('before','X'),('n',True),('n',-1),('post_n',1),('adult_w',float('nan')),('adult_w',float('inf')),('post_w',-1),('adult_w',0.5)]:
            z=copy.deepcopy(g);z[0][key]=val;bads.append(z)
        for z in bads:
            with self.assertRaises(ValueError):account(z)

    def test_input_not_mutated(self):
        g=grid([('U','R',1,1)]);before=copy.deepcopy(g);account(g);self.assertEqual(g,before)

class ClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.mapping=json.loads((HERE/'variable-map.json').read_bytes())
    def row(self,y=20,house='1',sr='5',post='2',party='Democratic'):
        m=self.mapping['waves'][str(y)];r={c:'NA' for c in [*m['party_fields'].values(),*m['party_post_fields'].values()]}
        r.update({m['house']:house,m['self_report']:sr,m['post']:post,m['file_status']:'1' if y==20 else 'Active',m['file_vote']:'1'})
        r[m['party_fields']['1']]=party;r[m['party_post_fields']['1']]=party
        return r,m
    def test_candidate_is_row_specific(self):
        for y in (20,22):
            for party,state in [('Democratic','D'),('Republican','R'),('Green','O')]:
                r,m=self.row(y,party=party);self.assertEqual(build.classify(r,m,y)[0],state)
    def test_2020_slot9_suffix(self):
        r,m=self.row(house='9');r['HouseCand9Party']='Republican';r['HouseCand9Party_post']='Republican';self.assertEqual(build.classify(r,m,20)[0],'R')
    def test_nonvoter_and_contest_abstention_distinct(self):
        for house,sr,state in [('11','5','A'),('12','1','N'),('NA','1','N'),('NA','NA','U'),('13','5','U')]:
            r,m=self.row(house=house,sr=sr);self.assertEqual(build.classify(r,m,20)[0],state)
    def test_conflicts_unknown(self):
        for house,sr in [('1','1'),('10','4'),('12','5')]:
            r,m=self.row(house=house,sr=sr);s,e=build.classify(r,m,20);self.assertEqual(s,'U');self.assertTrue(e['conflict'])
    def test_missing_questionnaire_not_nonvoter(self):
        r,m=self.row(post='1');s,e=build.classify(r,m,20);self.assertEqual(s,'U');self.assertEqual(e['self_report'],'unknown')
    def test_unmatched_does_not_override_ballot(self):
        for y in (20,22):
            r,m=self.row(y);r[m['file_status']]='NA' if y==20 else '-1';r[m['file_vote']]='NA'
            s,e=build.classify(r,m,y);self.assertEqual(s,'D');self.assertEqual(e['file_status'],'unmatched')
    def test_matched_no_record_not_nonvoter(self):
        for y in (20,22):
            r,m=self.row(y);r[m['file_vote']]='NA' if y==20 else '7';s,e=build.classify(r,m,y);self.assertEqual(s,'D');self.assertEqual(e['file_status'],'matched_no_record')
    def test_preference_cannot_fill_unknown(self):
        r,m=self.row(house='NA',sr='NA');r['CC20_412_nv']='1';self.assertEqual(build.classify(r,m,20)[0],'U')
    def test_party_missing_or_disagree(self):
        for value in ('NA','Republican'):
            r,m=self.row();r[m['party_fields']['1']]=value;self.assertEqual(build.classify(r,m,20)[0],'U')
    def test_malformed_codes_and_weights(self):
        self.assertIsNone(build.code('nan',(1,2)))
        for value in ('inf','-1','1.5','x'):
            with self.assertRaises(ValueError):build.code(value,(1,2))
        for value in ('-1','inf','x'):
            with self.assertRaises(ValueError):build.weight(value)

class ArtifactTests(unittest.TestCase):
    def test_pew_source_and_estimand_boundaries(self):
        j=json.loads((HERE/'pew-benchmark.json').read_bytes());meta=json.loads((HERE/'accounting.json').read_bytes())['meta']
        self.assertEqual(j['benchmark']['value_percent'],68);self.assertIsNone(j['benchmark']['denominator_n'])
        for k in ('source_sha256','spec_sha256','mapping_sha256'):self.assertEqual(j['meta'][k],meta[k])
        self.assertEqual(len(j['sources']),3)
        for s in j['sources']:
            self.assertTrue(s['url'].startswith('https://www.pewresearch.org/'));self.assertLessEqual(len(s['short_excerpt'].split()),25)
        txt=' '.join(j['limitations'])
        for required in ('总统','众议院','犹他','WEIGHT_W78_W117_VALIDATEDVOTE','不能','加权'):self.assertIn(required,txt)
    def test_readonly_recompute_and_summary_tampering(self):
        outputs=build.build();before={k:(HERE/k).read_bytes() for k in outputs}
        for name,data in outputs.items():self.assertEqual(before[name],data)
        # 检查器比较重算内容，JSON可解析并不能绕过篡改检查。
        bad=json.loads(before['accounting.json']);bad['modes']['unweighted']['known_delta']+=1
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            for name,data in outputs.items():(p/name).write_bytes(data)
            (p/'accounting.json').write_bytes(build.encode(bad))
            frozen={name:(p/name).read_bytes() for name in outputs}
            with self.assertRaises(ValueError):build.check_outputs(outputs,p)
            self.assertEqual(frozen,{name:(p/name).read_bytes() for name in outputs})
        self.assertEqual(before,{k:(HERE/k).read_bytes() for k in outputs})
    def test_mapping_and_input_hash_tamper_fail(self):
        for name in ('variable-map.json','source-manifest.json'):
            with tempfile.TemporaryDirectory() as temp:
                p=Path(temp)
                for file in ('design-seal.json','variable-map.json','source-manifest.json','analysis-spec.json'):
                    shutil.copy2(HERE/file,p/file)
                (p/'sources').mkdir();shutil.copy2(HERE/'sources/coding-frequency-check.json',p/'sources/coding-frequency-check.json')
                j=json.loads((p/name).read_bytes());j['tamper']=True;(p/name).write_bytes(build.encode(j))
                with self.assertRaises(ValueError):build.validate_design(p)
    def test_changed_source_bytes_fail_even_with_manifest_sealed(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            for file in ('design-seal.json','variable-map.json','source-manifest.json','analysis-spec.json'):
                shutil.copy2(HERE/file,p/file)
            (p/'sources').mkdir();shutil.copy2(HERE/'sources/coding-frequency-check.json',p/'sources/coding-frequency-check.json')
            source=p/'fake.csv';source.write_text('changed bytes',encoding='utf-8')
            manifest=json.loads((p/'source-manifest.json').read_bytes());manifest['sources']['two_wave_csv']['path']=str(source)
            (p/'source-manifest.json').write_bytes(build.encode(manifest))
            seal=json.loads((p/'design-seal.json').read_bytes());seal['files']['source-manifest.json']=build.sha(p/'source-manifest.json')
            (p/'design-seal.json').write_bytes(build.encode(seal))
            with self.assertRaisesRegex(ValueError,'输入哈希'):build.validate_design(p)

if __name__=='__main__':unittest.main()
