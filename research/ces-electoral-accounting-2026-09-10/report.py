"""由已核验机器表生成中文研究交接稿，检查模式不写文件。"""
import argparse,json,math
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(n):return json.loads((HERE/n).read_bytes())
def render():
    a=read('accounting.json');u=a['modes']['unweighted'];cells=read('flow-cells.json')['cells'];part=read('participation.json');bench=read('pew-benchmark.json')
    names={'D':'民主党','R':'共和党','O':'其他票','A':'未投众院','N':'未参加选举','U':'未知/冲突'}
    order=['D','R','O','A','N','U'];lookup={(c['before'],c['after']):c['n'] for c in cells}
    lines=['# 2020→2022众院票与参与：实施交接稿','',
    '**实施与核验完成，最终科学审核待后续。** 研究LH270／合同LH-304；主队列为现有两波发布的11,009人，不按2024留存筛选。', '',
    f"两期众院票状态均可解析者 {u['known_pair_n']:,} 人，至少一期未知或冲突者 {u['unknown_pair_n']:,} 人。已解析部分的签名贡献为 {u['known_delta']:+.0f}；这不是全队列点估计。将未知允许范围保留后，全队列总变化界限为 [{u['delta_bounds'][0]:+.0f}, {u['delta_bounds'][1]:+.0f}]，每百名队列成员为 [{u['per100_bounds'][0]:+.2f}, {u['per100_bounds'][1]:+.2f}]。界限跨零，本轮规则不能确定全队列变化方向。",'',
    '## 完整票流（人数）','', '| 2020→2022 | '+' | '.join(names[x] for x in order)+' | 合计 |','|'+'---|'*8]
    for x in order:lines.append('| '+names[x]+' | '+' | '.join(str(lookup[x,y]) for y in order)+' | '+str(sum(lookup[x,y] for y in order))+' |')
    lines+=['| 合计 | '+' | '.join(str(sum(lookup[x,y] for x in order)) for y in order)+' | 11009 |','',
    '## 已解析部分的互斥贡献','',
    '签名：R＝+1、D＝−1、其他票和明确无众院票＝0。正号表示共和党减民主党的签名余额增加；不是票份额百分点，也不是因果贡献。','',
    '| 转移类别 | 已知两端人数 | 已知签名贡献 | 含未知完成的分项界限 |','|---|---:|---:|---:|']
    cn={'repeat_vote_choice':'两期均有记录众院票：选择变化','election_entry':'明确未参加选举→有记录众院票','election_exit':'有记录众院票→明确未参加选举','contest_entry':'明确未投众院→有记录众院票','contest_exit':'有记录众院票→明确未投众院','other_zero':'其他已知零贡献转移'}
    for k,label in cn.items():
        c=u['components'][k];lines.append(f"| {label} | {c['known_n']} | {c['known_delta']:+.0f} | [{c['bounds'][0]:+.0f}, {c['bounds'][1]:+.0f}] |")
    lines+=['','分项界限的极端值不能任意相加；总界限独立求得。“未投众院”不单独证明参加过其他选举项目。所有界限以已解析自报为给定，不是抽样置信区间，也不涵盖已知回答可能错误的全部测量风险。','',
    '## 权重敏感性','', '| 口径 | 覆盖人数 | 缺权重人数 | 已知贡献 | 每百单位权重的总变化界限 |','|---|---:|---:|---:|---:|']
    for mode,label in [('unweighted','原始人数（主结果）'),('adult','固定2022成人权重'),('post','固定2022选后权重覆盖者')]:
        z=a['modes'][mode];lines.append(f"| {label} | {z['covered_n']} | {z['missing_weight_n']} | {z['known_delta']:+.3f} | [{z['per100_bounds'][0]:+.2f}, {z['per100_bounds'][1]:+.2f}] |")
    sr=part['transitions']['self_report'];tr={(x['before'],x['after']):x['n'] for x in sr};den=sum(x['n'] for x in sr if x['before']=='yes')
    lines+=['','两个时期对同人使用相同权重。成人加权仍是该队列的描述，不是全国恢复；选后权重缺失的1,263人不补零，也不从主表删除。','',
    '## 参与证据与Pew对照','',
    f"CES自报2020参与者共 {den:,} 人，其中2022自报参与 {tr['yes','yes']:,}、不参与 {tr['yes','no']:,}、未知 {tr['yes','unknown']:,}。在自报已知状态条件下，继续参与比例界限为 [{100*tr['yes','yes']/den:.2f}%, {100*(tr['yes','yes']+tr['yes','unknown'])/den:.2f}%]。另表完整保留两期档案有记录、匹配无记录和未匹配，均不自动替代自报状态。",'',
    f"Pew公布的相应参与背景数字为 {bench['benchmark']['value_percent']}%，使用其纵向加权及验证规则。CES的上述自报队列界限与Pew不是同一估计对象，不能相减成误差，也不能用Pew验证CES的众院转党率。Pew候选选择跨2020总统与2022众院两个职位。[公开报告]({bench['sources'][1]['url']})；具体规则见 [Pew对照卡](pew-comparison.md)。",'',
    '## 交回审核','',
    '保留LH269及changed414勘误，当前PID细化分支收口。下一次科学审核只需核对状态决策、未知界限、来源差异及新增证据的必要性；不得把已知部分的+237当作全队列或全国结论。未发布、未合并、未新增外部API分包。','',
    '复算入口见 [README](README.md)；逐格独立证据见 [verification.json](verification.json)；执行与重试见 [execution-provenance.json](execution-provenance.json)。','',
    f"输入SHA256：`{a['meta']['source_sha256']}`；规格SHA256：`{a['meta']['spec_sha256']}`；映射SHA256：`{a['meta']['mapping_sha256']}`。"]
    return ('\n'.join(lines)+'\n').encode('utf-8')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args();data=render();p=HERE/'report.md'
    if args.check:
        if p.read_bytes()!=data:raise ValueError('报告与核验表不一致')
    else:p.write_bytes(data)
    print(json.dumps({'report_check':args.check,'passed':True},ensure_ascii=False))
if __name__=='__main__':main()
