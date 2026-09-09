"""只用匿名矩阵充分统计复算恢复量，不重建个人数据。"""
import math
def summarize(s):
    n=s['n'];matrix=[[v/n for v in row] for row in s['matrix_totals']];R0=s['baseline_R_n']/n;R1=sum(matrix[a][2] for a in range(3))
    result={'n':n,'R22_pp':100*R1,'R_change_pp':100*(R1-R0),'D_to_R_pp':100*matrix[0][2],'R_to_D_pp':100*matrix[2][0],
            'I_to_R_pp':100*matrix[1][2],'R_to_I_pp':100*matrix[2][1],'D_to_I_pp':100*matrix[0][1],'I_to_D_pp':100*matrix[1][0],
            'gross_category_change_pp':100*sum(matrix[a][b] for a in range(3) for b in range(3) if a!=b),
            'R_nonzero_change_pp':100*(sum(matrix[a][2] for a in [0,1])+sum(matrix[2][b] for b in [0,1])),
            'matrix':matrix,'matrix_outside_probability_domain':any(v < -1e-10 or v>1+1e-10 for line in matrix for v in line)}
    if not math.isclose(sum(map(sum,matrix)),1,abs_tol=1e-10):raise ValueError('矩阵概率和不为1')
    return result
