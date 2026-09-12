"""流式读取两波原件，生成匿名票流和证据账本；--check只读复算。"""
import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from accounting_kernel import account, STATES

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
MISSING={'','NA','N/A','NAN','NULL','.'}
OTHER_PARTIES={'Libertarian','Independent','Conservative','Green','Working Families','Socialist Workers','Liberty','Working Class','Constitution','Independent American','United Utah','Alliance','Moderate','Unity','Center','No Party Preference'}

def encode(x):
    return (json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n').encode('utf-8')

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def missing(x):return x.strip().upper() in MISSING

def code(x,allowed):
    if missing(x):return None
    try:v=float(x)
    except ValueError:raise ValueError('类别不是数值') from None
    if not math.isfinite(v) or not v.is_integer() or int(v) not in allowed:raise ValueError('未核定类别编码')
    return int(v)

def weight(x):
    if missing(x):return None
    try:v=float(x)
    except ValueError:raise ValueError('权重不是数值') from None
    if not math.isfinite(v) or v<0:raise ValueError('权重负值或非有限')
    return v

def file_evidence(row,m,year):
    s,v=row[m['file_status']],row[m['file_vote']]
    if year==20:
        sc=code(s,range(1,6));vc=code(v,range(1,6))
        if sc is None and vc is None:return 'unmatched'
        if sc is None:raise ValueError('2020档案状态与方法矛盾')
        return 'matched_no_record' if vc is None else 'voted'
    vc=code(v,range(1,8))
    if s=='-1' and vc is None:return 'unmatched'
    if s=='Active' and vc in range(1,8):return 'matched_no_record' if vc==7 else 'voted'
    raise ValueError('2022档案编码或组合未核定')

def classify(row,m,year):
    """主票只使用有效选后自报；档案并列保存；规则来自封印映射。"""
    took=code(row[m['post']],(1,2))
    sr=code(row[m['self_report']],range(1,6))
    hc=code(row[m['house']],[int(x) for x in m['party_fields']]+[10,11,12,13])
    evidence={'post_status':'post' if took==2 else 'not_post' if took==1 else 'unknown_post',
              'self_report':'yes' if sr==5 else 'no' if sr is not None else 'unknown',
              'file_status':file_evidence(row,m,year),'reasons':[],'conflict':False,'file_self_disagreement':False}
    if took!=2:
        evidence['self_report']='unknown'
        evidence['reasons'].append(evidence['post_status'])
        if sr is not None or hc is not None:evidence['reasons'].append('response_outside_post')
        return 'U',evidence
    ballot=hc in [int(x) for x in m['party_fields']] or hc==10
    if hc is None:
        state='U';evidence['reasons'].append('missing_house_item')
    elif hc>=10:
        state=m['house_special'][str(hc)]
        if hc==13:evidence['reasons'].append('unsure_house')
    else:
        pre=row[m['party_fields'][str(hc)]];post=row[m['party_post_fields'][str(hc)]]
        if missing(pre):
            state='U';evidence['reasons'].append('unknown_party')
        elif not missing(post) and pre!=post:
            state='U';evidence['reasons'].append('party_mapping_conflict')
        elif pre in ('Democratic','Republican'):state='D' if pre=='Democratic' else 'R'
        elif pre in OTHER_PARTIES:state='O'
        else:raise ValueError('候选党派未核定')
    if (sr is not None and sr!=5 and ballot) or (sr==5 and hc==12):
        state='U';evidence['conflict']=True;evidence['reasons'].append('self_report_ballot_conflict')
    elif sr is not None and sr!=5:state='N'
    if sr is None:evidence['reasons'].append('missing_self_report')
    # 跨测量渠道不一致只作证据提示，不覆盖自报主票。
    evidence['file_self_disagreement']=(evidence['self_report']=='no' and evidence['file_status']=='voted') or (evidence['self_report']=='yes' and evidence['file_status']!='voted')
    return state,evidence

def validate_design(base):
    seal=json.loads((base/'design-seal.json').read_bytes())
    for name,digest in seal['files'].items():
        if sha(base/name)!=digest:raise ValueError('设计封印不符：'+name)
    manifest=json.loads((base/'source-manifest.json').read_bytes())
    for item in manifest['sources'].values():
        if sha(ROOT/item['path'])!=item['sha256']:raise ValueError('输入哈希不符：'+item['path'])
    for item in json.loads((base/'sources/coding-frequency-check.json').read_bytes()).values():
        if sha(ROOT/item['path'])!=item['sha256']:raise ValueError('年度编码证据原件改变')
    return manifest,json.loads((base/'variable-map.json').read_bytes()),json.loads((base/'analysis-spec.json').read_bytes())

def projected_rows(path,columns):
    with path.open(encoding='utf-8-sig',newline='') as f:
        rd=csv.reader(f);h=next(rd,[])
        if len(h)!=len(set(h)) or not set(columns)<=set(h):raise ValueError('表头重复或必需列缺失')
        ix={c:h.index(c) for c in columns}
        for r in rd:
            if len(r)!=len(h):raise ValueError('CSV行宽不一致')
            yield {c:r[i].strip() for c,i in ix.items()}

def csv_bytes(rows):
    out=io.StringIO(newline='');wr=csv.DictWriter(out,fieldnames=list(rows[0]),lineterminator='\n')
    wr.writeheader();wr.writerows(rows);return out.getvalue().encode('utf-8')

def build(base=HERE):
    manifest,mapping,spec=validate_design(base)
    meta={'schema_version':1,'research_label':'LH270','contract_id':'LH-304','source_sha256':manifest['sources']['two_wave_csv']['sha256'],'spec_sha256':sha(base/'analysis-spec.json'),'mapping_sha256':sha(base/'variable-map.json')}
    required=set(mapping['id_columns'])|set(mapping['weight_columns'].values())
    for m in mapping['waves'].values():
        required.update(m[k] for k in ('post','self_report','house','file_status','file_vote'))
        required.update(m['party_fields'].values());required.update(m['party_post_fields'].values())
    cells={(a,b):{'before':a,'after':b,'n':0,'adult_ws':[],'post_ws':[],'post_n':0} for a in STATES for b in STATES}
    evidence=defaultdict(lambda:{'n':0,'adult_ws':[],'post_ws':[],'post_n':0})
    ids=[set(),set()];raw=defaultdict(Counter);reason_counts=defaultdict(Counter);unknown_reasons=defaultdict(Counter)
    n=post_missing=post_zero=0
    for row in projected_rows(ROOT/manifest['sources']['two_wave_csv']['path'],sorted(required)):
        for i,col in enumerate(mapping['id_columns']):
            v=row[col]
            if missing(v) or v in ids[i]:raise ValueError('连接键缺失或重复')
            ids[i].add(v)
        adult=weight(row[mapping['weight_columns']['adult']]);pw=weight(row[mapping['weight_columns']['post']])
        if adult is None or adult<=0:raise ValueError('全队列成人正权重预期不符')
        if pw is None:post_missing+=1
        elif pw==0:post_zero+=1
        states=[];ev=[]
        for year in (20,22):
            m=mapping['waves'][str(year)];s,e=classify(row,m,year);states.append(s);ev.append(e)
            for k in ('post','self_report','house','file_status','file_vote'):raw[m[k]][row[m[k]]]+=1
            for reason in e['reasons']:
                reason_counts[str(year)][reason]+=1
                if s=='U':unknown_reasons[str(year)][reason]+=1
        def add(bucket):
            bucket['n']+=1;bucket['adult_ws'].append(adult)
            if pw is not None:bucket['post_n']+=1;bucket['post_ws'].append(pw)
        add(cells[tuple(states)])
        pair_key=tuple(str(e[k]) for e in ev for k in ('post_status','self_report','file_status','conflict','file_self_disagreement'))
        add(evidence[pair_key]);n+=1
    if n!=spec['cohort_n'] or n-post_missing!=spec['expected_weight_coverage']['post'] or post_missing!=1263 or post_zero:
        raise ValueError('队列/权重覆盖预期不符')
    def finish(v):
        z=dict(v);z['adult_w']=math.fsum(z.pop('adult_ws'));z['post_w']=math.fsum(z.pop('post_ws'));return z
    cs=[finish(c) for c in cells.values()]
    result=account(cs)
    result.update(meta=meta,limitations=[spec['scientific_status'],spec['uncertainty'],'已知贡献仅包含两端均已解析者，不能代表整个队列点估计。','A与N分开：A到D/R/O仅说明众院票项进入，不一定是从未参加选举变为参加。'])
    erows=[]
    enames=[f'{k}_{y}' for y in (20,22) for k in ('post_status','self_report','file_status','conflict','file_self_disagreement')]
    for key,value in sorted(evidence.items()):erows.append(dict(zip(enames,key),**finish(value)))
    transitions={}
    for kind,stateset in [('self_report',['yes','no','unknown']),('file_status',['voted','matched_no_record','unmatched'])]:
        tr=[]
        for a in stateset:
            for b in stateset:
                rr=[r for r in erows if r[kind+'_20']==a and r[kind+'_22']==b]
                tr.append({'before':a,'after':b,'n':sum(r['n'] for r in rr),'adult_w':math.fsum(r['adult_w'] for r in rr),'post_n':sum(r['post_n'] for r in rr),'post_w':math.fsum(r['post_w'] for r in rr)})
        transitions[kind]=tr
    audit={'meta':meta,'n':n,'id_unique_counts':[len(x) for x in ids],'raw_counts':raw,'reason_counts':reason_counts,'unknown_reason_counts':unknown_reasons,'reason_note':'原因标签可能重叠，不能相加作未知人数。','post_missing_n':post_missing,'post_zero_n':post_zero,'required_columns':sorted(required),'no_2024_read':not any('24' in c for c in required),'no_preference_items':not any('_nv' in c for c in required)}
    closed={'meta':meta,'cells':cs}
    data_rows=[dict(**meta,**c) for c in cs]
    return {'flow-cells.json':encode(closed),'flow.csv':csv_bytes(data_rows),'accounting.json':encode(result),'participation-evidence.csv':csv_bytes([dict(**meta,**r) for r in erows]),'participation.json':encode({'meta':meta,'transitions':transitions,'note':'自报参与和档案记录分别核算，不把无档案记录视为确定未投票。'}),'input-audit.json':encode(audit)}

def check_outputs(outputs,directory):
    for name,data in outputs.items():
        target=directory/name
        if not target.is_file() or target.read_bytes()!=data:raise ValueError('复算产物不符：'+name)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.add_argument('--directory',type=Path,default=HERE);args=ap.parse_args()
    outputs=build(args.directory)
    if args.check:check_outputs(outputs,args.directory)
    else:
        for name,data in outputs.items():(args.directory/name).write_bytes(data)
    print(json.dumps({'passed':True,'check':args.check,'n':11009,'grid':36,'products':list(outputs)},ensure_ascii=False))

if __name__=='__main__':main()
