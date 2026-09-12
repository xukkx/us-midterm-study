# 使用survey的设计协方差；保留全选后设计框，再建立共同应答域。
suppressPackageStartupMessages(library(survey))
options(survey.lonely.psu='fail')
out <- 'research/anes-class-identity-2026-09-11'
run <- 'runs/run-323'
savejson <- function(x, name) jsonlite::write_json(x,file.path(out,name),pretty=TRUE,auto_unbox=TRUE,null='null',digits=16)
d <- read.csv(file.path(run,'local-analysis-frame.csv'),na.strings=c('','NA'),stringsAsFactors=FALSE)
d$domain <- d$domain=='True'; d$support <- d$support=='True'
frame <- d[d$scope=='fresh' & !is.na(d$weight),]
stopifnot(nrow(frame)==2694,all(frame$weight>0),all(!is.na(frame$psu)),all(!is.na(frame$stratum)))
for(v in c('PID','income','owner','age','sample','phone','C'))frame[[v]]<-factor(frame[[v]])
des <- svydesign(ids=~psu,strata=~stratum,weights=~weight,data=frame,nest=TRUE)
domain <- subset(des,domain)
z <- domain$variables
cells <- table(factor(z$E,levels=0:1),factor(z$I,levels=0:1),factor(z$Y,levels=0:1))
di <- list(R=R.version.string,survey=as.character(packageVersion('survey')),frame_n=nrow(frame),domain_n=nrow(z),frame_df=degf(des),domain_df=degf(domain),cells=unname(as.vector(cells)),frame_psus=nrow(unique(frame[,c('stratum','psu')])),frame_strata=length(unique(frame$stratum)),fits_attempted=0)
fail <- function(reason){savejson(list(status='fit_not_supported',reason=reason,diagnostics=di,spec_version='LH271-1.0'),'fit_not_supported.json');quit(status=0)}
if(any(cells<10)||sum(z$support)==0||degf(domain)<=18)fail('support_or_design_df_gate_failed')
forms <- list(M0=Y~E+PID+income+owner+age+sample+phone,M1=Y~E+PID+income+owner+age+sample+phone+I+C,M2=Y~E+PID+income+owner+age+sample+phone+I+C+E:I)
fits<-list();diagmodels<-list();coefs<-list()
for(n in names(forms)){
 mm<-model.matrix(forms[[n]],z)
 if(qr(mm)$rank<ncol(mm))fail(paste(n,'rank_deficient'))
 warnings<-character()
 di$fits_attempted<-di$fits_attempted+1
 f<-tryCatch(withCallingHandlers(svyglm(forms[[n]],design=domain,family=quasibinomial(),control=glm.control(maxit=60,epsilon=1e-9)),warning=function(w){warnings<<-c(warnings,conditionMessage(w));invokeRestart('muffleWarning')}),error=function(e)e)
 if(inherits(f,'error'))fail(paste(n,conditionMessage(f)))
 info<-list(n=nrow(model.frame(f)),rank=f$rank,columns=ncol(mm),converged=f$converged,iterations=f$iter,max_abs_coef=max(abs(coef(f))),fitted_range=range(fitted(f)),warnings=warnings,condition=kappa(mm),residual_df=f$df.residual)
 diagmodels[[n]]<-info
 if(!f$converged || length(warnings)>0 || any(!is.finite(coef(f))) || info$max_abs_coef>20 || min(fitted(f))<1e-8 || max(fitted(f))>1-1e-8 || info$condition>1e8)fail(paste(n,'convergence_separation_condition_gate_failed'))
 fits[[n]]<-f;coefs[[n]]<-data.frame(model=n,term=names(coef(f)),estimate=unname(coef(f)),se=sqrt(diag(vcov(f))))
}
stopifnot(length(unique(vapply(fits,function(f)nrow(model.frame(f)),integer(1))))==1)
f<-fits$M2;s<-z[z$support,];w<-s$weight/sum(s$weight)
mats<-list();preds<-list();gradient<-rep(0,length(coef(f)));delta<-0
for(j in seq_len(4)){
 ei<-list(c(1,1),c(0,1),c(1,0),c(0,0))[[j]];sign<-c(1,-1,-1,1)[j]
 nd<-s;nd$E<-ei[1];nd$I<-ei[2]
 mm<-model.matrix(delete.response(terms(f)),nd,contrasts.arg=f$contrasts)
 p<-plogis(drop(mm%*%coef(f)));mats[[j]]<-mm;preds[[j]]<-p
 delta<-delta+sign*sum(w*p)
 gradient<-gradient+sign*colSums(mm*as.vector(w*p*(1-p)))
}
# Delta方法的梯度交给survey::svycontrast；不自行计算调查方差或重造PSU影响量。
names(gradient)<-names(coef(f));lin<-svycontrast(f,list(delta_gradient=gradient));se<-as.numeric(SE(lin))
# 独立中心差分核对梯度；不是新增模型拟合。
fun<-function(b) sum(vapply(seq_len(4),function(j)c(1,-1,-1,1)[j]*sum(w*plogis(drop(mats[[j]]%*%b))),numeric(1)))
numeric_grad<-sapply(seq_along(coef(f)),function(k){b<-coef(f);b[k]<-b[k]+1e-5;up<-fun(b);b[k]<-b[k]-2e-5;(up-fun(b))/2e-5})
stopifnot(max(abs(numeric_grad-gradient))<1e-7)
crit<-qt(.975,df=f$df.residual)
res<-list(spec_version='LH271-1.0',status='associational_only',primary=list(estimand='fixed_empirical_S_probability_DID',estimate=delta,se=se,interval_95=delta+c(-1,1)*crit*se,interval_method='survey_delta_t_conditional_on_empirical_S',residual_df=f$df.residual,n_support=nrow(s),weight_support=sum(s$weight),n_domain=nrow(z),support_fraction=nrow(s)/nrow(z),gradient_check_max_error=max(abs(numeric_grad-gradient))),diagnostics=c(di,list(models=diagmodels)),causal_effect=FALSE,prospective_validation=FALSE)
savejson(res,'associational_results.json')
write.csv(do.call(rbind,coefs),file.path(out,'model_coefficients.csv'),row.names=FALSE)
write.csv(data.frame(case=s$case,weight=s$weight,m11=preds[[1]],m01=preds[[2]],m10=preds[[3]],m00=preds[[4]]),file.path(run,'local-standardization.csv'),row.names=FALSE)
saveRDS(list(fits=fits,design=des),file.path(run,'local-survey-fit.rds'))
capture.output(sessionInfo(),file=file.path(run,'R-session-info.txt'))
print(res$primary)
