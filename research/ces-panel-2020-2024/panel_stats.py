import math
_VALID={"pid":("D","R"),"house":("D","R"),"president":("D","R"),"turnout":("matched_no_record","voted"),"medicare":("oppose","support"),"drug_price":("oppose","support"),"immigration":("oppose","support")}
def _ok(x):
 return not isinstance(x,bool) and isinstance(x,(int,float)) and math.isfinite(float(x))
def _rr(r):
 try:
  a,b,c=r["positive_n"],r["w"],r["w2"]
 except KeyError:
  raise ValueError("充分统计缺字段")
 for v in (a,b,c):
  if not _ok(v) or float(v)<0:
   raise ValueError("权重或计数非法")
 if int(a)!=a or (a==0 and (b!=0 or c!=0)) or (a>0 and (b<=0 or c<=0)):
  raise ValueError("正权重人数与加权和矛盾")
 if b*b>a*c+1e-9*max(1,b*b,a*c):
  raise ValueError("权重充分统计违反平方和约束")
 return float(a),float(b),float(c)
def estimate(rows,values):
 # 每格常量值x,加权均值与固定权重精度诊断
 if len(rows)!=len(values):
  raise ValueError("测量值与格数不一致")
 P=[];W=[];Q=[];X=[]
 for r,x in zip(rows,values):
  if not _ok(x):
   raise ValueError("测量值非法")
  a,b,c=_rr(r)
  P.append(a);W.append(b);Q.append(c);X.append(float(x))
 n=int(sum(P));S=float(sum(W));S2=float(sum(Q))
 sup=n<80;low=80<=n<=99
 eff=S*S/S2 if S>0 and S2>0 else None
 if n<80 or n==0 or S<=0:
  return {"n":n,"W":S,"W2":S2,"n_eff":eff,"mean":None,"unweighted_mean":None,"se":None,"ci95":None,"suppressed":sup,"low_n":low}
 m=sum(b*x for b,x in zip(W,X))/S
 u=sum(a*x for a,x in zip(P,X))/n
 if n<2:
  return {"n":n,"W":S,"W2":S2,"n_eff":eff,"mean":m,"unweighted_mean":u,"se":None,"ci95":None,"suppressed":sup,"low_n":low}
 s=sum(q*(x-m)**2 for q,x in zip(Q,X))
 se=math.sqrt(n/(n-1)*s)/S
 ci=[m-1.96*se,m+1.96*se]
 return {"n":n,"W":S,"W2":S2,"n_eff":eff,"mean":m,"unweighted_mean":u,"se":se,"ci95":ci,"suppressed":sup,"low_n":low}
def pair_table(cells,from_year,to_year):
 # 同组同measure同权重跨波联合格,按两波状态合并
 e0=estimate([],[])
 c0=dict(e0);c0["change_pp"]=None;c0["ci95_pp"]=None
 if not cells:
  return {"from_year":from_year,"to_year":to_year,"raw_n":0,"eligible_n":0,"W":0.0,"n_eff":None,"matrix":[],"paired":{"raw_n":0,"eligible_n":0,"excluded_eligible_n":0,"W":0.0,"n_eff":None,"before":e0,"after":e0,"change":c0},"directions":[]}
 ms=set();ys=None;gr=set();wt=set()
 for c in cells:
  ms.add(c.get("measure"))
  for k in ("group","group_id"):
   if k in c:
    gr.add(c[k])
  for k in ("weight","weight_name"):
   if k in c:
    wt.add(c[k])
  y=tuple(c.get("years",[]))
  if ys is None:
   ys=y
  elif y!=ys:
   raise ValueError("年份结构不一致")
  if len(c.get("states",[]))!=len(y):
   raise ValueError("状态与年份长度不一致")
 if len(ms)!=1:
  raise ValueError("混合测量")
 if len(gr)>1 or len(wt)>1:
  raise ValueError("混合群体或权重")
 if from_year not in ys or to_year not in ys or from_year==to_year:
  raise ValueError("非法比较年份")
 if len(set(ys))!=len(ys) or next(iter(ms)) not in _VALID:
  raise ValueError("重复年份或未登记测量")
 ms0=next(iter(ms));vd=_VALID.get(ms0,())
 tm=vd[1] if len(vd)==2 else None
 i=ys.index(from_year);j=ys.index(to_year)
 ag={}
 for c in cells:
  st=c["states"];k=(st[i],st[j])
  a,b,d=_rr(c);rn=c.get("n",c.get("positive_n",0))
  if not _ok(rn) or float(rn)<0 or int(rn)!=rn or rn<a:
   raise ValueError("原始人数非法或小于正权重人数")
  o=ag.get(k)
  if o is None:
   ag[k]=[float(rn),a,b,d]
  else:
   o[0]+=float(rn);o[1]+=a;o[2]+=b;o[3]+=d
 tP=sum(v[1] for v in ag.values());tW=sum(v[2] for v in ag.values())
 mt=[]
 for fs,ts in sorted(ag,key=lambda k:(str(k[0]),str(k[1]))):
  rn,pn,w,w2=ag[(fs,ts)]
  if tP<80 or tW<=0:
   ws=us=None
  else:
   ws=w/tW;us=pn/tP if tP>0 else None
  mt.append({"from_state":fs,"to_state":ts,"n":int(rn),"positive_n":int(pn),"w":w,"w2":w2,"weighted_share":ws,"unweighted_share":us})
 el=[r for r in mt if r["from_state"] in vd and r["to_state"] in vd] if vd else []
 eP=sum(r["positive_n"] for r in el);eR=sum(r["n"] for r in el)
 eW=sum(r["w"] for r in el);eW2=sum(r["w2"] for r in el)
 eff=eW*eW/eW2 if eW>0 and eW2>0 else None
 rawN=int(sum(v[0] for v in ag.values()))
 bf=estimate(el,[1.0 if r["from_state"]==tm else 0.0 for r in el]) if el else estimate([],[])
 af=estimate(el,[1.0 if r["to_state"]==tm else 0.0 for r in el]) if el else estimate([],[])
 ch=estimate(el,[(1.0 if r["to_state"]==tm else 0.0)-(1.0 if r["from_state"]==tm else 0.0) for r in el]) if el else estimate([],[])
 ch["change_pp"]=None if ch["mean"] is None else 100.0*ch["mean"]
 ch["ci95_pp"]=None if ch["ci95"] is None else [100.0*ch["ci95"][0],100.0*ch["ci95"][1]]
 ds=[]
 if len(vd)==2:
  for a,b in ((vd[0],vd[1]),(vd[1],vd[0])):
   sb=[r for r in el if r["from_state"]==a]
   es=estimate(sb,[1.0 if r["to_state"]==b else 0.0 for r in sb]) if sb else estimate([],[])
   d={"from_state":a,"to_state":b};d.update(es);ds.append(d)
 pr={"raw_n":eR,"eligible_n":eP,"excluded_eligible_n":int(tP-eP),"W":eW,"n_eff":eff,"before":bf,"after":af,"change":ch}
 total_w2=sum(v[3] for v in ag.values())
 total_eff=tW*tW/total_w2 if total_w2>0 else None
 return {"from_year":from_year,"to_year":to_year,"raw_n":rawN,"eligible_n":int(tP),"W":tW,"n_eff":total_eff,"matrix":mt,"paired":pr,"directions":ds}
