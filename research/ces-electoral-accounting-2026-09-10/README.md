# LH270：众院票与参与核算（待审）

研究LH270／实施合同LH-304；公开提交合同LH-305。先读[报告](report.md)。本轮保持PID研究收口，不晋级预测器。

## 公开复算

从仓库根目录运行 `python -X utf8 -B research/ces-electoral-accounting-2026-09-10/public_check.py`。它检查载荷哈希、从匿名36格表复算三种权重下的贡献与界限、核对报告并运行核算和分类合成测试，不需要个人原件。

`verification.json`是已经实际执行的本地原件独立复核记录；公开匿名格表不能替代该验证。`build.py`和`verify.py`保留本地实现供代码审阅，其原件模式需要原始CSV及本地登记材料，公开仓库不附这些材料。`test_accounting.py`中的ArtifactTests也依赖该本地环境，未冒称可在公开仓库运行。

`local-design-seal.json`保存原运行前封印；其中原本地输入清单的字节不可由删减后的`public-source-manifest.json`替代。公开转换与原始摘要见`publication-provenance.json`。没有改变规格、映射、数值结果或报告字节。

Pew只作参与变化背景；其2020总统与2022众院候选选择不能作为CES同职位转党验证。最终科学审核仍待进行；本提交不表示已合并或批准结论。
