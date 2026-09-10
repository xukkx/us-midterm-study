# LH269离线复算

本目录自含匿名联合格、冻结预测、支持审计和匹配信息集检验；不含受访者标识或原始CSV。仅需Python标准库。

在本目录执行：

~~~text
python -X utf8 -B -m unittest discover -s . -p "test_*.py"
python -X utf8 -B support_audit.py --check
python -X utf8 -B matched_test.py --check
python -X utf8 -B verify.py --check
python -X utf8 -B report.py --check
python -X utf8 -B matched_test.py --reproduce
~~~

前五项重建确定性结果或核验全部99,999份已存档随机统计；最后一项才重新抽取99,999次并与封存文件逐字节比较。不得把快速检查描述为完整随机重放。

report.md为中文结论，foundations.md登记数学对象与边界，analysis-plan.json是计算前固定的回顾性计划。support-summary.csv为10行支持汇总，support-audit.csv为544行折×特征×目标明细。matched-null.json.gz保存固定种子的全部零参考统计，checksums位于downloads/checksums.json。

LH268目录及其结果保持原字节；本目录报告勘误的changed414总分仅修正汇总，未修改任何模型。分包执行及未采用输出的限制见execution-provenance.json。
