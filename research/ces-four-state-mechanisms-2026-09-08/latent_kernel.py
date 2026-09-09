"""监督者的结构测量映射；无外部依赖，不将潜标签当心理事实。"""
import math
from matrix4 import matmul4 as multiply,inverse4
def emission(e):return [[(1-e)*int(i==j)+e/4 for j in range(4)] for i in range(4)]
def reconstruct(P,e0,e1):
    if len(P)!=4 or any(len(r)!=4 for r in P):raise ValueError('只接受4×4联合表')
    if any(not math.isfinite(v) or v<0 for r in P for v in r) or not math.isclose(math.fsum(v for r in P for v in r),1,abs_tol=1e-10,rel_tol=0):raise ValueError('联合概率非法')
    if any(not math.isfinite(e) or not 0<=e<1 for e in (e0,e1)):raise ValueError('测量参数非法')
    Q=multiply(multiply(inverse4(e0),P),inverse4(e1));E0,E1=emission(e0),emission(e1);again=multiply(multiply(E0,Q),E1)
    return {'Q':Q,'E0':E0,'E1':E1,'reconstructed':again,'max_error':max(abs(P[i][j]-again[i][j]) for i in range(4) for j in range(4)),
            'feasible':min(v for r in Q for v in r)>=-1e-12,'latent_R_change':math.fsum(Q[i][2] for i in range(4))-math.fsum(Q[2]),'gross_change':1-math.fsum(Q[i][i] for i in range(4))}
