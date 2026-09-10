"""公开匿名载荷复算，不依赖个人原件。"""
import hashlib,json,subprocess,sys
from pathlib import Path
from accounting_kernel import account
import report
P=Path(__file__).resolve().parent
def read(n):return json.loads((P/n).read_bytes())
manifest=read('public-manifest.json')
for name,digest in manifest['files'].items():
    if hashlib.sha256((P/name).read_bytes()).hexdigest()!=digest:raise ValueError('公开载荷哈希改变：'+name)
if account(read('flow-cells.json')['cells'])['modes']!=read('accounting.json')['modes']:raise ValueError('匿名汇总复算不符')
if report.render()!=(P/'report.md').read_bytes():raise ValueError('报告不符')
q=subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','test_accounting.KernelTests','test_accounting.ClassificationTests','-v'],cwd=P)
if q.returncode:raise SystemExit(q.returncode)
print(json.dumps({'passed':True,'anonymous_cells':36,'modes':3,'raw_microdata_rerun':False,'payloads_checked':len(manifest['files'])},ensure_ascii=False))
