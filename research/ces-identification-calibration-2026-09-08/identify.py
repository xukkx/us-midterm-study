"""原始不确定类型到两个明确不同的全队列目标；含可达端点见证。"""
import argparse,itertools,json,math
from fractions import Fraction
from common import *
from bounds_kernel import bound,support

def members(atom):return groups_from_flags(atom['latino_employed'],atom['r_renter'])
def select(atoms,g,c='full'):
    return [a for a in atoms if g in members(a) and (c=='full' or a['s']==(c=='retained'))]
def flat(b):return {k:v for k,v in b.items() if not k.endswith('_witness')}
def verify_witness(cells,result,convention,weighted,coef=None):
    for side in ('lower','upper'):
        ws=result[side+'_witness'];assert len(ws)==len(cells)
        mass=[c['w'] if weighted else c['n'] for c in cells]
        for c,w in zip(cells,ws):
            assert w['before_value'] in support(c['before'],convention) and w['after_value'] in support(c['after'],convention)
            assert (w['n'],w['w'])==(c['n'],c['w'])
        z=math.fsum(m*(w['after_value']-w['before_value'])*(coef[i] if coef is not None else 1) for i,(m,w) in enumerate(zip(mass,ws)))
        if coef is None:z/=math.fsum(mass)
        assert math.isclose(z,result[side],abs_tol=1e-12)

def compute(data):
    atoms=data['atoms'];rows=[];contrasts=[];witnesses=[]
    for convention in ('resolved','literal'):
        for g in GROUPS:
            for weighted in (False,True):
                by={}
                for c in COHORTS:
                    cells=select(atoms,g,c);v=bound(cells,convention,weighted);verify_witness(cells,v,convention,weighted)
                    n=sum(x['n'] for x in cells);w=math.fsum(x['w'] for x in cells)
                    row={'convention':convention,'group':g,'cohort':c,'weighted':weighted,'n':n,'weight_total':w,'lower_pp':100*v['lower'],'upper_pp':100*v['upper'],
                         'unknown_people':sum(x['n'] for x in cells if any(len(support(x[k],convention))>1 for k in ['before','after'])),
                         'unknown_endpoints':sum(x['n']*sum(len(support(x[k],convention))>1 for k in ['before','after']) for x in cells)}
                    if not weighted:
                        for side in ('lower','upper'):
                            numerator=sum(x['n']*(x['after_value']-x['before_value']) for x in v[side+'_witness'])
                            row[side+'_fraction']=str(Fraction(numerator,n))
                    by[c]=row;rows.append(row)
                    witnesses.append({'target':'cohort_mean','convention':convention,'group':g,'cohort':c,'weighted':weighted,'cells':cells,**v})
                assert by['full']['n']==by['retained']['n']+by['omitted']['n']
                cells=select(atoms,g);mass='w' if weighted else 'n';total=math.fsum(x[mass] for x in cells);ret=math.fsum(x[mass] for x in cells if x['s'])
                coef=[(1/ret if x['s'] else 0)-1/total for x in cells]
                v=bound(cells,convention,weighted,coef);verify_witness(cells,v,convention,weighted,coef)
                q=ret/total
                assert math.isclose(100*v['lower'],(1-q)*(by['retained']['lower_pp']-by['omitted']['upper_pp']),abs_tol=1e-10)
                assert math.isclose(100*v['upper'],(1-q)*(by['retained']['upper_pp']-by['omitted']['lower_pp']),abs_tol=1e-10)
                contrasts.append({'convention':convention,'group':g,'weighted':weighted,'retained_mass_share':q,'lower_pp':100*v['lower'],'upper_pp':100*v['upper'],'strictly_positive':v['lower']>1e-12,'necessarily_above_2pp':100*v['lower']>2})
                witnesses.append({'target':'retained_minus_full','convention':convention,'group':g,'weighted':weighted,'cells':cells,'coefficient':coef,**v})
    # 观察完整案例的协方差等式和总移动率，以原始格独立计算。
    observed=[]
    for g in GROUPS:
        cs=[x for x in select(atoms,g) if x['before'] in ('D','I','R') and x['after'] in ('D','I','R')]
        for weighted in (False,True):
            mass='w' if weighted else 'n';T=math.fsum(x[mass] for x in cs);R=math.fsum(x[mass] for x in cs if x['s']);r=R/T
            d=lambda x:int(x['after']=='R')-int(x['before']=='R')
            full=math.fsum(x[mass]*d(x) for x in cs)/T
            kept=math.fsum(x[mass]*d(x) for x in cs if x['s'])/R
            omitted=math.fsum(x[mass]*d(x) for x in cs if not x['s'])/(T-R)
            cov=math.fsum(x[mass]*(x['s']-r)*(d(x)-full) for x in cs)/T
            assert math.isclose(kept-full,cov/r,abs_tol=1e-12)
            assert math.isclose(kept-full,(1-r)*(kept-omitted),abs_tol=1e-12)
            flow={}
            for label,s in [('retained',1),('omitted',0)]:
                sub=[x for x in cs if x['s']==s];den=math.fsum(x[mass] for x in sub)
                flow[label]={'any_category_change_pp':100*math.fsum(x[mass] for x in sub if x['before']!=x['after'])/den,
                             'R_indicator_nonzero_pp':100*math.fsum(x[mass] for x in sub if d(x)!=0)/den}
            observed.append({'group':g,'weighted':weighted,'n':sum(x['n'] for x in cs),'retained_share':r,'full_delta_pp':100*full,'retained_delta_pp':100*kept,'omitted_delta_pp':100*omitted,'B_pp':100*(kept-full),'covariance_over_r_pp':100*cov/r,'flows':flow})
    overlap={a:{b:sum(x['n'] for x in atoms if a in members(x) and b in members(x)) for b in GROUPS} for a in GROUPS}
    return {'rows':rows,'selection_contrasts':contrasts,'complete_case':observed,'group_overlap_n':overlap,
            'bound_kind':'固定队列可行端点，不是95%区间；群体重叠，边际上下界不是可任意组合的联合盒子。'},witnesses

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    result,witnesses=compute(json.loads((HERE/'pid-atoms.json').read_bytes()))
    for name,v in [('identification-results.json',result),('endpoint-witnesses.json',witnesses)]:
        b=encode(v);path=HERE/name
        if a.check:
            if path.read_bytes()!=b:raise ValueError('界限或见证复算不符')
        else:path.write_bytes(b)
    print(json.dumps({'rows':len(result['rows']),'contrasts':len(result['selection_contrasts']),'witness_targets':len(witnesses),'check':a.check},ensure_ascii=False))
if __name__=='__main__':main()
