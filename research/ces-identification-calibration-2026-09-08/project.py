"""原件到匿名识别格和本地遮蔽投影；绝不输出逐人记录。"""
import argparse,csv,hashlib,json,math
from collections import Counter,defaultdict
from pathlib import Path
from common import *
BASE=('pid7_20','race_20','hispanic_20','employ_20','ownhome_20','CC20_410','CC20_327a')
def read(path,cols):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        rd=csv.reader(f);h=next(rd,[])
        if not h or len(h)!=len(set(h)) or not set(cols)<=set(h):raise ValueError('表头为空、重复或缺列')
        ix={c:h.index(c) for c in cols}
        for line in rd:
            if len(line)!=len(h):raise ValueError('CSV行宽非法')
            yield {c:line[i].strip() for c,i in ix.items()}

def make(baseline,selected,private):
    source=json.loads((HERE/'source-manifest.json').read_bytes())
    if sha(baseline)!=source['baseline_sha256'] or sha(selected)!=source['selected_sha256']:raise ValueError('原件哈希不符')
    sel={};wave22=set()
    for r in read(selected,['caseid_20','caseid_22',*BASE]):
        k=r['caseid_20'];j=r['caseid_22']
        if k.upper() in MISS or j.upper() in MISS or k in sel or j in wave22:raise ValueError('三波键缺失或重复')
        sel[k]=r;wave22.add(j)
    extra=['caseid','caseid_22','pid7_22','commonweight_22','birthyr_20','educ_20']
    fields=[*BASE,*extra]
    # 信息获取审计：只检查已有选后候选人党派能否补已有槽位缺失，不计算众院效应。
    for y in (20,22):
        fields += [f'CC{y}_412',f'tookpost_{y}']
        for i in range(1,10 if y==20 else 9):
            fields += [('HouseCand9Party' if (y,i)==(20,9) else f'HouseCand{i}Party_{y}'),('HouseCand9Party_post' if (y,i)==(20,9) else f'HouseCand{i}Party_post_{y}')]
    ids=set();keys22=set();atoms={};masked=[];truth=[];types={y:Counter() for y in ('20','22')};Hmissing=Counter();candidates={str(y):{'selected_pre_missing_n':0,'resolved_by_existing_post_n':0} for y in (20,22)}
    for r in read(baseline,fields):
        k,j=r['caseid'],r['caseid_22']
        if k.upper() in MISS or j.upper() in MISS or k in ids or j in keys22:raise ValueError('两波键缺失或重复')
        ids.add(k);keys22.add(j);s=int(k in sel)
        if s and any(r[c]!=sel[k][c] for c in (*BASE,'caseid_22')):raise ValueError('基线字段或2022键不一致')
        p0,p1=pid(r['pid7_20']),pid(r['pid7_22'])
        types['20'][p0]+=1;types['22'][p1]+=1
        race=category(r['race_20'],range(1,9));his=category(r['hispanic_20'],(1,2));emp=category(r['employ_20'],range(1,10));own=category(r['ownhome_20'],(1,2,3))
        l=(race==3 or his==1) and emp in (1,2);rr=p0=='R' and own==2
        w=num(r['commonweight_22'])
        if w is None or w<=0:raise ValueError('全队列固定权重要求每个人权重为正')
        key=(int(l),int(rr),s,p0,p1);v=atoms.setdefault(key,{'n':0,'weights':[]});v['n']+=1;v['weights'].append(w)
        for y in (20,22):
            slot=category(r[f'CC{y}_412'],list(range(1,10 if y==20 else 9))+[10,11,12,13])
            if slot is not None and slot<10 and r[f'tookpost_{y}']=='2':
                pre='HouseCand9Party' if (y,slot)==(20,9) else f'HouseCand{slot}Party_{y}'
                post='HouseCand9Party_post' if (y,slot)==(20,9) else f'HouseCand{slot}Party_post_{y}'
                if r[pre].upper() in MISS:
                    candidates[str(y)]['selected_pre_missing_n']+=1
                    if r[post].upper() not in MISS:candidates[str(y)]['resolved_by_existing_post_n']+=1
        if p0 not in ('D','I','R') or p1 not in ('D','I','R'):continue
        by=category(r['birthyr_20'],range(1900,2003));ed=category(r['educ_20'],range(1,7))
        agecat=3 if by is None else 0 if 2020-by<40 else 1 if 2020-by<65 else 2
        edu=2 if ed is None else int(ed>=5)
        Hmissing['age_missing']+=by is None;Hmissing['educ_missing']+=ed is None;Hmissing['housing_missing']+=own is None
        uid=hashlib.sha256(('LH263-fold-v1:'+k).encode()).hexdigest()
        rec={'key':uid,'fold':int(uid[:16],16)%5,'s':s,'y0':('D','I','R').index(p0),'y':('D','I','R').index(p1) if s else None,
             'housing':0 if own==1 else 1 if own==2 else 2,'latino_employed':int(l),'age':agecat,'education':edu,'groups':groups_from_flags(l,rr)}
        masked.append(rec);truth.append({'key':uid,'y':('D','I','R').index(p1)})
    if not set(sel)<=ids:raise ValueError('三波存在两波外个案')
    atomic=[]
    for (l,r,s,a,b),v in sorted(atoms.items()):
        atomic.append({'latino_employed':l,'r_renter':r,'s':s,'before':a,'after':b,'n':v['n'],'w':math.fsum(v['weights']),'w2':math.fsum(x*x for x in v['weights'])})
    assert len(masked)==10742 and len(ids)==11009 and len(sel)==6175
    private=Path(private);private.mkdir(exist_ok=True)
    for name,rows in [('masked-input.jsonl',masked),('scoring-truth.jsonl',truth)]:
        with (private/name).open('w',encoding='utf-8',newline='\n') as f:
            for row in rows:f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    audit={'raw_n':len(ids),'selected_n':len(sel),'omitted_n':len(ids)-len(sel),'key_unique_nonmissing':True,'baseline7_and_wave22_disagreement_n':0,
           'pid_raw_types':{y:dict(v) for y,v in types.items()},'candidate_information_audit':candidates,'calibration_n':len(masked),'calibration_S1_n':sum(r['s'] for r in masked),
           'H_missing':dict(Hmissing),'fold_counts':dict(Counter(r['fold'] for r in masked)),
           'masked_input_sha256':sha(private/'masked-input.jsonl'),'truth_file_sha256':sha(private/'scoring-truth.jsonl'),'S0_outcome_hidden':all(r['y'] is None for r in masked if not r['s'])}
    write(HERE/'pid-atoms.json',{'atoms':atomic,'source_hashes':source,'target':'未复制个人记录的互斥基线成员×S×原始PID类型充分格表'})
    write(HERE/'projection-audit.json',audit)
    print(json.dumps({'raw_n':len(ids),'S1_n':len(sel),'calibration_n':len(masked),'atoms':len(atomic),'pid_types':audit['pid_raw_types']},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',required=True);p.add_argument('--selected',required=True);p.add_argument('--private',required=True);a=p.parse_args();make(a.baseline,a.selected,a.private)
