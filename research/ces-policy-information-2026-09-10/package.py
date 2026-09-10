"""构建匿名自含ZIP并在隔离目录实际复算。"""
import hashlib,json,os,platform,subprocess,sys,tempfile,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
FILES=["analysis-plan.json","foundations.md","README.md","report.md","report.py","verify.py","independent_audit.py","test_verification.py","test_information_identity.py","test_matched.py","test_support.py","test_rejection.py","support_audit.py","matched_test.py","joint-counts.json","history-nested.json","decomposition.json","challenger.json","comparison.json","support-audit.json","support-audit.csv","support-summary.csv","matched-test.json","matched-null.json.gz","verification.json","execution-provenance.json","package.py"]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def commands():
    return [('-m','unittest','discover','-s','.','-p','test_*.py'),('support_audit.py','--check'),('matched_test.py','--check'),('verify.py','--check'),('report.py','--check'),('matched_test.py','--reproduce')]
def main():
    dest=HERE/'downloads';dest.mkdir(exist_ok=True)
    checks={n:sha(HERE/n) for n in FILES}
    (dest/'checksums.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    archive=dest/'ces-policy-information-2026-09-10.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name in sorted(FILES+['checksums.json']):
            source=dest/name if name=='checksums.json' else HERE/name
            info=zipfile.ZipInfo(name,(2026,9,10,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,source.read_bytes())
    records=[]
    with tempfile.TemporaryDirectory(prefix='lh269-portable-') as tmp:
        t=Path(tmp)
        with zipfile.ZipFile(archive) as z:z.extractall(t)
        assert all(sha(t/n)==h for n,h in checks.items())
        for args in commands():
            argv=[sys.executable,'-X','utf8','-B',*args];q=subprocess.run(argv,cwd=t,capture_output=True,text=True,encoding='utf-8',timeout=240,env={**os.environ,'PYTHONUTF8':'1'})
            records.append({'argv':argv,'exit_code':q.returncode,'output':q.stdout+q.stderr})
            if q.returncode:raise RuntimeError(records[-1])
    result={'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'public_files':FILES,'portable_checks':records,'runtime':{'python':sys.version,'platform':platform.platform()}}
    run=HERE.parents[1]/'runs/run-320';run.mkdir(parents=True,exist_ok=True)
    (run/'package-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'files':len(FILES),'commands':len(records),'zip_sha256':sha(archive)},ensure_ascii=False))
if __name__=='__main__':main()
