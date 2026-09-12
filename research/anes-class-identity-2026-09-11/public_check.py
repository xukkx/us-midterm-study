"""公开匿名结果检查；不冒称重做原件分析。"""
import sys,hashlib,json,csv,subprocess
from pathlib import Path
P=Path(__file__).parent
for n,h in json.loads((P/'public-manifest.json').read_text(encoding='utf8'))['files'].items():
 assert hashlib.sha256((P/n).read_bytes()).hexdigest()==h,n
rows=list(csv.DictReader((P/'denominator_and_material_identity_tables.csv').open(encoding='utf8')))
den={r['cell']:int(r['n']) for r in rows if r['table']=='denominator'}
assert den['panel']+den['PAPI']+den['fresh']==den['all']==5521
assert sum(int(r['n']) for r in rows if r['table']=='fresh_vote')==den['fresh']==3105
assert sum(int(r['n']) for r in rows if r['table']=='domain_E_I_Y')==den['domain']==1835
assert sum(int(r['n']) for r in rows if r['table']=='fresh_E_I_vote')==den['fresh']
assert den['support']==793 and len(rows)==578
assert not any(r['table']=='item_raw_codes' and ':V240001:' in r['cell'] for r in rows)
from report import render
assert render()==(P/'report.md').read_text(encoding='utf8')
q=subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s',str(P),'-p','test_*.py','-v'])
assert q.returncode==0
print(json.dumps({'passed':True,'table_rows':len(rows),'tests':9,'raw_data_rerun':False,'survey_fits_rerun':False}))
