"""仅本地读取原始CSV，核对来源并输出匿名计数；不修改LH260材料。"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from retention_core import build_counts

BASE_SHA='946afde863a1c1319bb2931bbd24650961aedae27f36e6447ecdc7db68f83c4c'
SELECTED_SHA='e9921d391159cf8fcb68a0b69aa76c94a5bf73436f516606bf3fb310125ba5ac'
FIELDS=('pid7','race','hispanic','employ','ownhome','CC20_410','CC20_327a')

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def read_rows(path, selected=False):
    mapping={f:f if f.startswith('CC20_') or not selected else f+'_20' for f in FIELDS}
    mapping['id']='caseid_20' if selected else 'caseid'
    with path.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream);header=reader.fieldnames or []
        if len(header)!=len(set(header)) or not set(mapping.values())<=set(header):
            raise ValueError('重复表头或缺少必要字段')
        for row in reader:
            if None in row or any(v is None for v in row.values()):raise ValueError('行宽不完整')
            yield {key:row[col] for key,col in mapping.items()}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',required=True,type=Path)
    parser.add_argument('--selected',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if sha(args.baseline)!=BASE_SHA or sha(args.selected)!=SELECTED_SHA:raise ValueError('原始输入不属于已核定版本')
    counts=build_counts(read_rows(args.baseline),read_rows(args.selected,True),'2020_annual_to_2024_retained')
    counts['sources']={'baseline_sha256':BASE_SHA,'selected_sha256':SELECTED_SHA,'baseline_target':'2020年度完整文件，不是2022或2024邀请框','two_wave_status':'原件未取得，未计算两波到三波留存'}
    encoded=(json.dumps(counts,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')
    if args.check:
        if args.output.read_bytes()!=encoded:raise ValueError('原件到匿名计数不一致')
    else:args.output.write_bytes(encoded)
    print(json.dumps({'totals':counts['totals'],'anonymous_rows':len(counts['rows']),'check':args.check},ensure_ascii=False))

if __name__=='__main__':main()
