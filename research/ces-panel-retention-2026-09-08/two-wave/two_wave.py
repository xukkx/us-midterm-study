"""在冻结统计函数之外接入两波原件；微数据仅在本机读取。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from retention_core import build_counts
from summarize import summarize
from csv_reader import read_rows

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def check_wave_ids(baseline,selected):
    maps=[]
    for rows in (baseline,selected):
        seen=set();ids={}
        for row in rows:
            value=row['caseid_22'].strip()
            if value.upper() in ('','NA') or value in seen:
                raise ValueError('2022连接键缺失或重复')
            seen.add(value);ids[row['id']]=value
        maps.append(ids)
    if any(maps[0].get(key)!=value for key,value in maps[1].items()):
        raise ValueError('2022连接键跨文件不一致')

def build(baseline_path,selected_path):
    manifest=json.loads((HERE/'source-manifest.json').read_bytes())
    if sha(baseline_path)!=manifest['sha256'] or sha(selected_path)!=manifest['selected_source']['sha256']:
        raise ValueError('来源SHA256不一致')
    baseline=read_rows(baseline_path,'caseid')
    selected=read_rows(selected_path,'caseid_20')
    counts=build_counts(baseline,selected,'published_2022_to_2024_retained')
    check_wave_ids(baseline,selected)
    counts['sources']={'baseline_sha256':manifest['sha256'],
                       'selected_sha256':manifest['selected_source']['sha256'],
                       'target':'2022两波发布文件到2024三波发布文件的条件保留'}
    return counts

def summarize_counts(counts):
    result=summarize(counts)
    result.pop('two_wave_retention',None)
    result['two_wave_retention_status']='computed'
    result['target']='出现在2022两波发布文件者进入2024三波发布文件的条件保留比例；未加权，不是完整邀请框响应率'
    result['limits']=['官方指南11015人与实际两波11009人相差6人，原因未知；三波6175人全部连接',
                      '未进入三波文件不等于受邀拒访或没有投票，尚缺邀请、完成与质量检查过程标记',
                      '固定2020群体的构成描述，不能识别缺失者选票或选择偏差方向；不改LH260政治转移估计']
    return result

def encode(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')

def main():
    p=argparse.ArgumentParser()
    for name in ('baseline','selected','counts','results'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--check',action='store_true');a=p.parse_args()
    counts=build(a.baseline,a.selected);results=summarize_counts(counts)
    for path,value in ((a.counts,counts),(a.results,results)):
        content=encode(value)
        if a.check:
            if path.read_bytes()!=content:raise ValueError('复算字节不一致')
        else:path.write_bytes(content)
    print(json.dumps({'totals':counts['totals'],'anonymous_rows':len(counts['rows']),'check':a.check},ensure_ascii=False))

if __name__=='__main__':main()
