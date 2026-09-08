"""公开复现入口：离线，从县级输入与匿名汇总统计重算表格。"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'src'))
from midterms.ecological_bounds import density_stratified_profile

def read(name):
    return json.loads((HERE/'inputs'/name).read_text(encoding='utf-8'))

def verify_inputs():
    manifest = read('manifest.json')
    for name, info in manifest['files'].items():
        data = (HERE/'inputs'/name).read_bytes()
        if hashlib.sha256(data).hexdigest() != info['sha256']:
            raise ValueError('输入哈希不符：'+name)
    return manifest

def symmetric_components(composition, within, interaction):
    """对称分解平均分配交互项；名称仅描述算术项，不识别个人机制。"""
    return {'composition': composition+interaction/2, 'within_group': within+interaction/2}

def build():
    manifest = verify_inputs()
    with (HERE/'inputs/county-input.csv').open(encoding='utf-8',newline='') as stream:
        county = list(csv.DictReader(stream))
    assert len(county) == manifest['county_rows']
    assert len({(r['year'],r['fips']) for r in county}) == len(county)
    profiles = []
    for year in (2012,2016,2020,2024):
        records = [r for r in county if int(r['year'])==year]
        assert len(records) == manifest['county_counts'][str(year)]
        for group, num, den in [('hispanic','hispanic','total_pop'),('hs_or_less','hs_or_less','edu_total_25plus')]:
            rows = [{'x':int(r[num])/int(r[den]), 'y':int(r['rep_votes'])/(int(r['rep_votes'])+int(r['dem_votes'])), 'w':int(r['rep_votes'])+int(r['dem_votes'])} for r in records if int(r[den])>0]
            for row in density_stratified_profile(rows):
                selected = [r for r in rows if r['x'] >= row['threshold']]
                w = sum(r['w'] for r in selected)
                row.update(year=year, subgroup=group,
                    geographic_rep_share=sum(r['w']*r['y'] for r in selected)/w if w else None,
                    joined_vote_coverage=manifest['join_audit'][str(year)]['weight_coverage'])
                profiles.append(row)
    turnout = []
    for r in read('turnout-sufficient-statistics.json'):
        n, total, known, voted = (r[k] for k in ('sample_n','weighted_n','turnout_known_wn','turnout_voted_wn'))
        assert 0 <= voted <= known+1e-8 <= total+1e-7
        unknown = max(0.0,total-known)
        sufficient = n >= 80
        turnout.append({**r,'weight_variable':'weight_cumulative',
            'target':'当届CES中pid7=5–7、Own/Rent、有正人口权重的受访者',
            'known_status_rate':voted/known if sufficient and known else None,
            'unknown_as_nonvoter_rate':voted/total if sufficient and total else None,
            'unknown_as_voter_rate':(voted+unknown)/total if sufficient and total else None,
            'unknown_weight':unknown, 'unknown_weight_share':unknown/total if total else None,
            'voter_file_match_rate':None,'unweighted_known_n':None,'effective_n':None,
            'matched_only_rate':None,
            'missing_reason':'旧格账本未保留档案匹配标记、未加权已知数或权重平方和；未知敏感性仅针对账本外遗漏状态，不能替代匹配失败敏感性。'})
    annual=[]
    for r in read('annual-turnout-sufficient.json')['rows']:
        total,matched,voted=(r[k] for k in ('total_w','matched_w','voted_w'))
        assert 0 <= voted <= matched <= total
        sufficient=r['sample_n']>=80
        annual.append({**r,
            'weighted_match_rate':matched/total if sufficient and total else None,
            'recorded_vote_rate':voted/total if sufficient and total else None,
            'matched_only_rate':voted/matched if r['matched_n']>=80 and matched else None,
            'unmatched_all_voted_upper':(voted+total-matched)/total if sufficient and total else None,
            'effective_n':total*total/r['sum_w2'] if r['sum_w2'] else None,
            'registered_vote_rate':r['registered_voted_w']/r['registered_w'] if r['registered_n'] and r['registered_n']>=80 and r['registered_w'] else None})
    decomposition = []
    for r in read('decomposition.json'):
        v = symmetric_components(r['composition'],r['persuasion'],r['interaction'])
        assert math.isclose(sum(v.values()),r['delta_margin_R_minus_D'],abs_tol=1e-9)
        decomposition.append({'pair':r['pair'],'delta_margin_pp':r['delta_margin_R_minus_D']*100,
            'composition_pp':v['composition']*100,'within_group_pp':v['within_group']*100,
            'age_18_21_contribution_pp':r['first_time_total_contribution']*100,
            'interpretation':'重复横截面的人群构成与组内平均投票边际变化；18–21岁为年龄代理，不等于全部首投者。'})
    return {'schema_version':'validity-release.v1','ecological_profile':profiles,'renter_turnout_audit':turnout,
        'symmetric_decomposition':decomposition,'annual_match_audit':annual,
        'house_sensitivity':{'E':6.2,'center':.977,'legacy_coefficient':1.3308,'comparison_coefficient':.5,
            'environment_contribution_difference_pp':(1.3308-.5)*(6.2-.977),
            'interpretation':'固定中心和E的系数敏感性，既非胜率，也非任何系数的有效性证明。'}}

def fmt(x):
    return '未知' if x is None else f'{x:.2f}'

def markdown(rep):
    lines=['# 有效性更正的可复现表格','','## 县级密度分层剖面','',
        '县内全体选民的观测票份额与该县集中亚群的部分识别界是两个不同对象。覆盖分母是成功连接的县集；人口替代选民构成为显式假设。阈值越高不保证界宽更窄。','',
        '|年份|亚群|阈值|县数|县内亚群下界%|上界%|宽度pp|亚群权重覆盖%|县内全部票R份额%|',
        '|---|---|---|---|---|---|---|---|---|']
    for r in rep['ecological_profile']:
        vals=[r['year'],r['subgroup'],r['threshold'],r['counties']]+[fmt(r[k]*100 if r[k] is not None else None) for k in ('lower','upper','width','subgroup_weight_coverage','geographic_rep_share')]
        lines.append('|'+ '|'.join(map(str,vals))+'|')
    lines += ['','## 共和党租房者与房主：旧账本分母审计','',
        '同一人口权重下，分别使用旧已知状态分母、全部状态分母，以及把遗漏状态视为投票的极端上界。它们不是档案匹配失败者的敏感性分析。各年“匹配率”均为未知；不能把No Record当作“已匹配且未投票”。','',
        '|年份|居住|未加权n|加权总分母|已知状态分母|核验票权重|旧率%|遗漏状态计未投%|遗漏状态计投票%|',
        '|---|---|---|---|---|---|---|---|---|']
    for r in rep['renter_turnout_audit']:
        vals=[r['year'],r['tenure'],r['sample_n']]+[fmt(r[k]) for k in ('weighted_n','turnout_known_wn','turnout_voted_wn')]+[fmt(r[k]*100 if r[k] is not None else None) for k in ('known_status_rate','unknown_as_nonvoter_rate','unknown_as_voter_rate')]
        lines.append('|'+ '|'.join(map(str,vals))+'|')
    lines += ['','## 年度原始CSV：档案匹配敏感性审计','',
        '每年按该版代码本区别档案匹配和投票记录。人口权重：2016年commonweight_vv，2018年起commonweight；vvweight另列为登记选民目标。仅匹配率更换了人群，不能当作总体投票率的修正答案。上界假定未匹配者全都投票，也假定已匹配档案准确。','',
        '|年份|居住|n|匹配n|权重有效n|人口加权匹配%|记录票/全体%|记录票/已匹配%|未匹配全投上界%|登记权重票率%|',
        '|---|---|---|---|---|---|---|---|---|---|']
    for r in rep['annual_match_audit']:
        vals=[r['year'],r['tenure'],r['sample_n'],r['matched_n'],fmt(r['effective_n'])]+[fmt(r[k]*100 if r[k] is not None else None) for k in ('weighted_match_rate','recorded_vote_rate','matched_only_rate','unmatched_all_voted_upper','registered_vote_rate')]
        lines.append('|'+ '|'.join(map(str,vals))+'|')
    lines += ['','2010、2012、2014年度原始CSV当前缺失，匹配率仍未知。累计版与年度版不强求数值相同；两个版本及其权重的差异也是审计对象。2016登记权重目标与后续版不一致，保留未知。','',
        '## 对称shift-share分解','',
        '单位为R−D边际的百分点。对称形式把交互项平均分配给构成项和组内项。不能从组内项推断同一个人改变偏好。','',
        '|届对|总变化pp|构成pp|组内平均变化pp|18–21岁旧口径贡献pp|', '|---|---|---|---|---|']
    for r in rep['symmetric_decomposition']:
        lines.append('|'+r['pair']+'|'+'|'.join(fmt(r[k]) for k in ('delta_margin_pp','composition_pp','within_group_pp','age_18_21_contribution_pp'))+'|')
    lines += ['','## 众院参数敏感性','',f"固定E=6.2与中心0.977，系数1.3308和0.5的环境贡献相差{rep['house_sensitivity']['environment_contribution_difference_pp']:.6f}个百分点。这只衡量参数选择造成的差别。",'']
    return '\n'.join(lines)

def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--write',action='store_true');group.add_argument('--check',action='store_true')
    args=parser.parse_args(); rep=build()
    outputs={'tables.json':json.dumps(rep,ensure_ascii=False,sort_keys=True,indent=2)+'\n','tables.md':markdown(rep)}
    dest=HERE/'outputs'
    if args.write:
        dest.mkdir(parents=True,exist_ok=True)
        for n,s in outputs.items(): (dest/n).write_bytes(s.encode('utf-8'))
    else:
        for n,s in outputs.items():
            if not (dest/n).exists() or (dest/n).read_bytes()!=s.encode('utf-8'):
                raise SystemExit('复算不一致：'+n)
    print(json.dumps({'ok':True,'ecological_rows':len(rep['ecological_profile']),'turnout_rows':len(rep['renter_turnout_audit']),'annual_audit_rows':len(rep['annual_match_audit']),'decomposition_rows':len(rep['symmetric_decomposition'])}))

if __name__ == '__main__': main()
