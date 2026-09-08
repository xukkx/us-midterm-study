# analyze_panel.py: 固定权重留存配对精度诊断(标准库)
from panel_stats import estimate, pair_table
import argparse
import hashlib
import json
import sys
_P={"house":"post","president":"post"}
_R={"house":"registered22_post","president":"registered22_post"}
_M=("voted","matched_no_record")
_PS=[(2020,2022),(2020,2024),(2022,2024)]
def _pw(m):
 return _P.get(m,"population")
def _rw(m):
 return _R.get(m,"registered22")
def _ps(m):
 return [(2020,2024)] if m=="president" else list(_PS)
def analyze(data):
 cells=data["cells"]
 g0=data["groups"]
 measures={"pid","turnout","house","president","medicare","drug_price","immigration"}
 weights={"population","post","registered22","registered22_post"}
 sums={};keys=set()
 for c in cells:
  g,m,w=c["group"],c["measure"],c["weight"]
  if g not in g0 or m not in measures or w not in weights:
   raise ValueError("账本包含未登记群体、测量或权重")
  expected=[2020,2024] if m=="president" else [2020,2022,2024]
  if c["years"]!=expected or len(c["states"])!=len(expected):
   raise ValueError("账本年份或状态长度不完整")
  allowed=({"D","I","R","unknown"} if m=="pid" else
           {"voted","matched_no_record","unmatched"} if m=="turnout" else
           {"D","R","other","not_race","not_vote","unknown","not_post","unknown_post","missing_item","unknown_party"} if m in {"house","president"} else
           {"support","oppose","unknown"})
  if any(s not in allowed for s in c["states"]):
   raise ValueError("未登记状态不能并入阴性")
  n=c["n"]
  if isinstance(n,bool) or not isinstance(n,int) or n<0 or n<c["positive_n"]:
   raise ValueError("账本原始人数非法")
  estimate([c],[0])
  key=(g,m,w,tuple(c["states"]))
  if key in keys:
   raise ValueError("匿名状态格重复")
  keys.add(key);sums[(g,m,w)]=sums.get((g,m,w),0)+n
 for g,n in g0.items():
  if isinstance(n,bool) or not isinstance(n,int) or n<0:
   raise ValueError("群体人数非法")
  for m in measures:
   for w in weights:
    if sums.get((g,m,w),0)!=n:
     raise ValueError("账本人数未闭合或缺少测量")
 gs=set(g0.keys()) if isinstance(g0,dict) else set()
 for c in cells:
  if "group" in c:
   gs.add(c["group"])
 groups=sorted(gs,key=str)
 ms=sorted({c.get("measure") for c in cells if "measure" in c},key=str)
 ws=sorted({c.get("weight") for c in cells if "weight" in c},key=str)
 com=[]
 for g in groups:
  for m in ms:
   for role,w in (("primary",_pw(m)),("registered_sensitivity",_rw(m))):
    rs=[c for c in cells if c.get("group")==g and c.get("measure")==m and c.get("weight")==w]
    if not rs:
     continue
    for fy,ty in _ps(m):
     r=pair_table(rs,fy,ty)
     d={"group":g,"measure":m,"weight":w,"role":role}
     d.update(r)
     com.append(d)
 com.sort(key=lambda d:(str(d["group"]),str(d["measure"]),str(d["role"]),str(d["weight"]),d.get("from_year",0),d.get("to_year",0)))
 cov=[]
 for g in groups:
  for w in ws:
   rs=[c for c in cells if c.get("group")==g and c.get("weight")==w and c.get("measure")=="pid"]
   if not rs:
    continue
   e=estimate(rs,[0]*len(rs))
   raw=sum(int(c.get("n",c.get("positive_n",0))) for c in rs)
   cov.append({"group":g,"weight":w,"raw_n":raw,"positive_n":e["n"],"missing_or_zero_weight_n":raw-e["n"],"W":e["W"],"n_eff":e["n_eff"]})
 cov.sort(key=lambda d:(str(d["group"]),str(d["weight"])))
 tc=[]
 for g in groups:
  b=[c for c in cells if c.get("group")==g and c.get("measure")=="turnout" and c.get("weight")=="population"]
  if not b:
   continue
  ys=sorted({y for c in b for y in c.get("years",[])})
  for y in ys:
   rs=[c for c in b if y in c.get("years",[])]
   if not rs:
    continue
   mv=[1.0 if c["states"][c["years"].index(y)] in _M else 0.0 for c in rs]
   vv=[1.0 if c["states"][c["years"].index(y)]=="voted" else 0.0 for c in rs]
   me=estimate(rs,mv)
   ve=estimate(rs,vv)
   mr=[r for r,v in zip(rs,mv) if v==1.0]
   cv=[1.0 if r["states"][r["years"].index(y)]=="voted" else 0.0 for r in mr]
   ce=estimate(mr,cv) if mr else estimate([],[])
   tc.append({"group":g,"year":y,"matched":me,"voted":ve,"conditional_voted":ce})
 tc.sort(key=lambda d:(str(d["group"]),d["year"]))
 pe=[]
 for g in groups:
  for m,w in (("pid","population"),("house","post")):
   b=[c for c in cells if c.get("group")==g and c.get("measure")==m and c.get("weight")==w]
   if not b:
    continue
   kp=[]
   for c in b:
    ys=c.get("years",[])
    ss=c.get("states",[])
    i0=ys.index(2020);i1=ys.index(2022);i2=ys.index(2024)
    if ss[i0]=="D" and ss[i1]=="R" and ss[i2] in ("D","R"):
     kp.append(c)
   vv=[1.0 if c["states"][c["years"].index(2024)]=="R" else 0.0 for c in kp]
   e=estimate(kp,vv) if kp else estimate([],[])
   status="not_applicable_by_group_definition" if g=="R_renter_2020" and m=="pid" else "suppressed" if e["suppressed"] else "estimated"
   pe.append({"group":g,"measure":m,"from_year":2020,"middle_year":2022,"to_year":2024,"estimate":e,"status":status,
              "note":"该组2020年按定义属于R，D→R认同持续性不适用" if status=="not_applicable_by_group_definition" else "条件分母不足80时不发布比率"})
 pe.sort(key=lambda d:(str(d["group"]),str(d["measure"])))
 at={"invited_2024":11015,"completed_2024":7058,"qc_excluded_2024":883,"retained_2024":6175,"subgroup_attrition_rates":None,"completed_2022":11792,"qc_excluded_2022":780,"reported_retained_2022":11015,"note":"6175=7058-883；6175/61000不是单一流失率。2022代码本的11792减780等于11012，与所述11015相差3人；算术不一致尚未取得更正，不能擅改来源。"}
 li=["只是固定权重留存配对精度诊断,不估选择/匹配/总体设计误差。","登记权重针对2022登记选民,目标不同,不是成人稳健性。","未知不并入阴性,同波分子分母口径一致。","turnout_coverage描述保留样本的档案匹配与投票记录比例，不是实际总体投票率。","不作胜负或因果推断。"]
 return {"comparisons":com,"coverage":cov,"turnout_coverage":tc,"persistence":pe,"attrition":at,"limits":li}
def main(av=None):
 p=argparse.ArgumentParser()
 p.add_argument("--cells",required=True)
 p.add_argument("--output",required=True)
 p.add_argument("--check",action="store_true")
 o=p.parse_args(av)
 with open(o.cells,"rb") as f:
  raw=f.read()
 ch=hashlib.sha256(raw).hexdigest()
 data=json.loads(raw.decode("utf-8"))
 r=analyze(data)
 r["source"]={"cells_sha256":ch,"raw_csv_sha256":data.get("source_sha256"),"source_rows":data.get("source_rows")}
 t=json.dumps(r,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+"\n"
 exp=t.encode("utf-8")
 if o.check:
  try:
   cur=open(o.output,"rb").read()
  except FileNotFoundError:
   print("缺output",file=sys.stderr)
   return 1
  if cur!=exp:
   print("check不一致",file=sys.stderr)
   return 1
  print("comparisons=%d coverage=%d OK"%(len(r["comparisons"]),len(r["coverage"])))
  return 0
 with open(o.output,"wb") as f:
  f.write(exp)
 print("comparisons=%d coverage=%d OK"%(len(r["comparisons"]),len(r["coverage"])))
 return 0
if __name__=="__main__":
 sys.exit(main())
