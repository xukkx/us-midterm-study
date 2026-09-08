"""用CES年度CSV重算档案匹配审计，仅导出党派×居住的聚合充分统计。"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

SPECS = {
 2016: ('CCES16_Common_OUTPUT_Feb2018_VV.csv','commonweight_vv','CL_matched','CL_E2016GVM','CCES Guide 2016.pdf'),
 2018: ('CCES18_Common_OUTPUT_vv_topost.csv','commonweight','CL_matched','CL_2018gvm','CCES Guide 2018.pdf'),
 2020: ('CES20_Common_OUTPUT_vv.csv','commonweight','CL_voter_status','CL_2020gvm','CCES Guide 2020.pdf'),
 2022: ('CCES22_Common_OUTPUT_vv_topost.csv','commonweight','TS_voterstatus','TS_g2022','CES Guide 2022.pdf'),
 2024: ('CCES24_Common_OUTPUT_vv_topost_final.csv','commonweight','TS_voterstatus','TS_g2024','CES_2024_GUIDE_vv.pdf'),
}
MISSING={'','NA','NaN'}
def number(x):
    if x in MISSING:return None
    v=float(x)
    if not math.isfinite(v) or v<0:raise ValueError('权重须非负有限')
    return v

def classify(year,row):
    """按已读年度代码本显式转换，未知编码直接拒绝。"""
    _,_,mf,vf,_=SPECS[year]
    pid=row['pid7'];ten=row['ownhome']
    republican=pid in {'5','5.0','6','6.0','7','7.0','Lean Republican','Not very strong Republican','Strong Republican'}
    tenure={'1':'own','1.0':'own','Own':'own','2':'rent','2.0':'rent','Rent':'rent'}.get(ten)
    m=row[mf];v=row[vf]
    if year in (2016,2018):
        if m not in {'Y','N','Yes','No'}:raise ValueError('未识别匹配编码')
        matched=m in {'Y','Yes'}
    else:
        if m not in MISSING | ({'1','2','3','4','5'} if year==2020 else {'1'}):raise ValueError('未识别状态编码')
        matched=m not in MISSING
    vote_values={'polling','unknown','earlyVote','absentee','mail'} if year<2020 else ({'1','2','3','4','5'} if year==2020 else {'1','2','3','4','5','6'})
    if v not in vote_values | MISSING | ({'7'} if year>=2022 else set()):raise ValueError('未识别投票编码')
    voted=v in vote_values
    if voted and not matched:raise ValueError('存在投票记录但无档案匹配，须人工审查')
    return republican,tenure,matched,voted

def extract(rawdir):
    out=[];sources=[]
    for year,(file,wf,mf,vf,guide) in SPECS.items():
        path=rawdir/file
        stats={ten:{'sample_n':0,'matched_n':0,'voted_n':0,'total_w':0.,'sum_w2':0.,'matched_w':0.,'voted_w':0.,'registered_n':0,'registered_w':0.,'registered_voted_w':0.} for ten in ('rent','own')}
        total_rows=0
        with path.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                total_rows+=1
                rep,ten,matched,voted=classify(year,row)
                if not rep or ten is None:continue
                w=number(row[wf])
                if w is None or w==0:continue
                c=stats[ten];c['sample_n']+=1;c['matched_n']+=int(matched);c['voted_n']+=int(voted)
                c['total_w']+=w;c['sum_w2']+=w*w;c['matched_w']+=w*matched;c['voted_w']+=w*voted
                if year>=2018:
                    vw=number(row['vvweight'])
                    if vw:
                        c['registered_n']+=1;c['registered_w']+=vw;c['registered_voted_w']+=vw*voted
        expected={2016:64600,2020:61000}.get(year,60000)
        if total_rows!=expected:raise ValueError(f'{year}完整年度行数不符：{total_rows}')
        for ten,c in stats.items():
            if year==2016:
                for k in ('registered_n','registered_w','registered_voted_w'):c[k]=None
            out.append(dict(year=year,tenure=ten,population_weight=wf,match_field=mf,vote_field=vf,**c))
        sources.append({'year':year,'file':file,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rows':total_rows,
            'guide':guide,'guide_sha256':hashlib.sha256((rawdir/guide).read_bytes()).hexdigest()})
    return {'sources':sources,'rows':out,'not_available_years':[2010,2012,2014],
        'boundary':'年度文件版本与累计文件并不相同；匹配与仅匹配者投票率是测量审计，不是同一人退出的估计。'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--raw-dir',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();r=extract(args.raw_dir)
    args.output.write_bytes((json.dumps(r,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'ok':True,'years':len(r['sources']),'aggregate_rows':len(r['rows'])}))

if __name__=='__main__':main()
