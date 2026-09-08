"""从匿名人数复算入选比例及构成；抑制仅在输出层。"""
import argparse,json
from pathlib import Path

GROUPS=('all','Latino_employed_2020','R_renter_2020')
CATEGORIES={'overall':('all',),'pid':('D','I','R','unknown'),'employment':('full_time','part_time','other','unknown'),'tenure':('rent','own','other','unknown')}

def rate(numerator,denominator):
    if not isinstance(numerator,int) or isinstance(numerator,bool) or not isinstance(denominator,int) or isinstance(denominator,bool) or not 0<=numerator<=denominator:
        raise ValueError('比率分子分母非法')
    return {'numerator':numerator,'denominator':denominator,'value':numerator/denominator if denominator>=80 else None,'suppressed':denominator<80,'low_n':80<=denominator<100}

def summarize(counts):
    rows=counts['rows'];lookup={}
    for r in rows:
        key=(r['group'],r['dimension'],r['category'])
        if key in lookup:raise ValueError('匿名计数重复')
        if key[0] not in GROUPS or key[1] not in CATEGORIES or key[2] not in CATEGORIES[key[1]]:raise ValueError('未登记群体/维度/类别')
        for name in ('baseline_n','selected_n','not_selected_n'):
            v=r[name]
            if isinstance(v,bool) or not isinstance(v,int) or v<0:raise ValueError('人数非法')
        if r['selected_n']+r['not_selected_n']!=r['baseline_n']:raise ValueError('入选与未入选人数不闭合')
        lookup[key]=r
    expected={(g,d,c) for g in GROUPS for d,cs in CATEGORIES.items() for c in cs}
    if set(lookup)!=expected:raise ValueError('缺少固定匿名格，零人数不能省略')
    for g in GROUPS:
        total=lookup[(g,'overall','all')]
        for d in ('pid','employment','tenure'):
            for field in ('baseline_n','selected_n','not_selected_n'):
                if sum(lookup[(g,d,c)][field] for c in CATEGORIES[d])!=total[field]:raise ValueError('分层不闭合')
    total=lookup[('all','overall','all')]
    for key in ('baseline_n','selected_n','not_selected_n'):
        if counts['totals'][key]!=total[key]:raise ValueError('总体与分层人数不一致')
    if counts['totals']['unmatched_selected_n']!=0 or counts['totals']['matched_selected_n']!=total['selected_n']:
        raise ValueError('原件连接尚未通过')
    mismatch=counts['totals']['baseline_field_mismatches']
    if (any(mismatch.values()) if isinstance(mismatch,dict) else mismatch!=0):raise ValueError('基线字段存在差异')
    output=[]
    for key in sorted(lookup):
        r=lookup[key];g,d,c=key;gt=lookup[(g,'overall','all')]
        output.append({**r,'inclusion':rate(r['selected_n'],r['baseline_n']),
                       'baseline_composition':rate(r['baseline_n'],gt['baseline_n']),
                       'selected_composition':rate(r['selected_n'],gt['selected_n']),
                       'not_selected_composition':rate(r['not_selected_n'],gt['not_selected_n'])})
    return {'schema_version':1,'target':'2020年度文件到2024三波发布样本的跨阶段入选；不是邀请框响应率','rows':output,'totals':counts['totals'],'two_wave_retention':None,'limits':['两波原件尚未取得，11009与指南11015差6人待核验','未进入三波包含多个阶段，不等于受邀拒访或真实不投票','仅未加权描述，不据此识别2024选票偏差方向，不修改LH260估计']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--counts',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--check',action='store_true');a=p.parse_args()
    result=summarize(json.loads(a.counts.read_bytes()));encoded=(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')
    if a.check:
        if a.output.read_bytes()!=encoded:raise ValueError('复算结果字节不一致')
    else:a.output.write_bytes(encoded)
    print(json.dumps({'anonymous_rows':len(result['rows']),'totals':result['totals'],'check':a.check},ensure_ascii=False))

if __name__=='__main__':main()
