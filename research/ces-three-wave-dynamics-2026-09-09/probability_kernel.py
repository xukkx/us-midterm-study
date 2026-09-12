def joint(pi, T01, T12, E, y):
    # 时刻0前向：初分布乘发射
    a0 = [pi[i]*E[i][y[0]] for i in range(len(pi))]
    # 时刻1前向：经T01转移再乘发射
    a1 = [E[j][y[1]]*sum(a0[i]*T01[i][j] for i in range(len(pi))) for j in range(len(pi))]
    # 时刻2前向：经T12转移再乘发射
    a2 = [E[k][y[2]]*sum(a1[j]*T12[j][k] for j in range(len(pi))) for k in range(len(pi))]
    # 对末时刻求和得序列概率
    return sum(a2)  # LH265_COMPLETE
