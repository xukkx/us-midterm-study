import math
# 计算跨时间发射分布漂移：仅度量分布差异
# emissions: 三套KxM概率矩阵，时间对齐，不重排标签
# w: K个中间态权重，不解释为误分率
def drift_metrics(emissions, w):
  # K为状态数，T为时间点数
  K=len(w)
  T=len(emissions)
  # per_state[k]为该状态跨时间对TV距离最大值
  per_state=[]
  for k in range(K):
    m=0.0
    for t in range(T):
      for u in range(t+1,T):
        tv=0.5*math.fsum(abs(emissions[t][k][j]-emissions[u][k][j]) for j in range(len(emissions[t][k])))
        if tv>m: m=tv
    per_state.append(m)
  # maximum为所有状态与时间对上TV最大值
  maximum=max(per_state) if per_state else 0.0
  # weighted_average为按w加权的平均漂移
  weighted_average=math.fsum(w[k]*per_state[k] for k in range(K))
  return {'maximum':maximum,'per_state':per_state,'weighted_average':weighted_average}
# LH266_COMPLETE
