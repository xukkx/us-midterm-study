"""小型有界等式LP的精确有理数基可行解枚举；不是通用大规模求解器。"""
from fractions import Fraction
from itertools import combinations
from math import comb,isfinite

def Q(v):
    if isinstance(v,bool):raise ValueError('布尔量不是系数')
    if isinstance(v,float) and not isfinite(v):raise ValueError('系数非有限')
    return Fraction(str(v)) if not isinstance(v,Fraction) else v

def reduce_rows(A,b):
    mat=[[Q(x) for x in row]+[Q(v)] for row,v in zip(A,b)]
    n=len(A[0]);rank=0
    for col in range(n):
        pivot=next((i for i in range(rank,len(mat)) if mat[i][col]),None)
        if pivot is None:continue
        mat[rank],mat[pivot]=mat[pivot],mat[rank]
        d=mat[rank][col];mat[rank]=[x/d for x in mat[rank]]
        for i in range(len(mat)):
            if i!=rank and mat[i][col]:
                d=mat[i][col];mat[i]=[a-d*b for a,b in zip(mat[i],mat[rank])]
        rank+=1
        if rank==len(mat):break
    for row in mat[rank:]:
        if all(x==0 for x in row[:n]) and row[-1]!=0:raise ValueError('约束不相容')
    return [r[:n] for r in mat[:rank]],[r[-1] for r in mat[:rank]]

def solve(A,b):
    AA,bb=reduce_rows(A,b)
    if len(AA)!=len(A):return None
    return bb

def vertices(A,b,max_bases=100000):
    if not A or len(A)!=len(b) or not A[0] or any(len(r)!=len(A[0]) for r in A):raise ValueError('等式维度非法')
    n=len(A[0]);origA=[[Q(v) for v in r] for r in A];origb=[Q(v) for v in b]
    # 至少一个正系数总量约束，使每个非负变量都有有限上界。
    if not any(all(v>0 for v in row) and z>=0 for row,z in zip(origA,origb)):
        raise ValueError('未给全变量正系数总量约束，不接受无界或未知有界性问题')
    A,b=reduce_rows(origA,origb);m=len(A)
    if comb(n,m)>max_bases:raise ValueError('问题超过小型枚举预算')
    found=set()
    for basis in combinations(range(n),m):
        B=[[r[i] for i in basis] for r in A]
        try:v=solve(B,b)
        except ValueError:continue
        if v is None or any(x<0 for x in v):continue
        x=[Fraction(0)]*n
        for j,y in zip(basis,v):x[j]=y
        if any(sum(q*z for q,z in zip(r,x))!=y for r,y in zip(origA,origb)):raise AssertionError('基解没有满足原约束')
        found.add(tuple(x))
    if not found:raise ValueError('非负可行集为空')
    return sorted(found)

def optimize(A,b,c,denominator=None):
    """可选线性分式目标仅在分母对整个多面体严格为正时接受。"""
    vs=vertices(A,b);c=[Q(x) for x in c]
    if len(c)!=len(vs[0]):raise ValueError('目标维度非法')
    den=None if denominator is None else [Q(x) for x in denominator]
    if den is not None and len(den)!=len(c):raise ValueError('分母维度非法')
    values=[]
    for x in vs:
        y=sum(a*z for a,z in zip(c,x))
        if den is not None:
            d=sum(a*z for a,z in zip(den,x))
            if d<=0:raise ValueError('条件分母可为零或负，目标并非全域有定义')
            y/=d
        values.append((y,x))
    low,high=min(values),max(values)
    return {'lower':low[0],'upper':high[0],'lower_witness':low[1],'upper_witness':high[1],
            'vertices_checked':len(vs),'domain':'非负实数多面体；非整数LP不自动声称每个可行值为实际整数队列','target':'linear_fractional' if den is not None else 'linear'}
