# LH271：物质处境、身份与总统票（待审）

先读[研究报告](report.md)与[交回摘要](REVIEW_PACKET.md)。主关联方向未明确；不签署因果机制结论，也不替代LH270最终审核。

从仓库根运行 `python -X utf8 -B research/anes-class-identity-2026-09-11/public_check.py`，核对公开文件哈希、匿名分母闭合、报告生成和9项合成/完整性测试。

这项公开检查不重跑原始问卷分析或调查模型。`verification.json`、`validation-summary.json`记录已实际完成的本地验证；`build.py`、`verify.py`、`fit.R`与`check_package.py`供审阅，但依赖未公开的本地原件和运行文件。`local-checksums.json`是原本地封印的原样副本，不能把它当公开复算清单。公开清单见`public-manifest.json`。R脚本只删除本机专用库路径，读者需自行准备survey与jsonlite。

本目录不含个人CSV、逐人派生行、个体标准化概率、R拟合对象、凭证或私有附件。模型失败及监督者返工如实保留在执行说明中。提交不表示合并或科学结论获批准。
