"""LH266维护函数的独立可携带副本，发布前核验函数AST相同。"""
import math
def loglik(counts,p):
 if len(counts)!=64 or any(type(n)!=int or n<0 for n in counts) or sum(counts)==0:raise ValueError('似然仅接受64格非负整数人数，拒绝权重及有符号矩阵')
 if len(p)!=64 or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in p) or abs(sum(p)-1)>1e-8:raise ValueError('须为64格有效观察概率')
 if any(n>0 and v==0 for n,v in zip(counts,p)):raise ValueError('正频数格的模型概率为零，拒绝不可能候选')
 return sum(n*math.log(v) for n,v in zip(counts,p) if n)
