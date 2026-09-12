# LH263.1：安全子组区间与完整匿名核验

新评审的两个缺陷均已重现。旧标准化子组点值−50pp，却附上中心−20pp的区间；旧匿名校验器对空rows返回0检查成功。

`uncertainty(rows, method, fitting_population=完整拟合预测行)`现在要求标准化明确提供完整拟合人群，且只支持该完整人群。任何子集，包括由整个标准化格组成的子组，均返回invalid和`unsupported_standardization_subgroup`。省略上下文返回`fitting_population_required`。这避免把残差增强估计的区间附在纯标准化点值上；尚未实现包含组外训练影响的子组方差，不以重新定中心掩盖该问题。

匿名校验器现在按键匹配准确九个唯一群体×方法组合，并必须完成36检查；空、缺项、不同长度、重复或意外组合均显式失败。顺序不同但组合完整的输入仍可核验。

以下命令在原LH263研究目录中执行：

```powershell
python -X utf8 -B -m unittest discover -s . -p 'test_*.py'
python -X utf8 -B anonymous_benchmark.py
python -X utf8 -B simulate.py --check
```

原实证结果、原600次模拟、输入、计划和模型/预测封印保持原字节；仅维修代码、新增测试、校验清单及复现ZIP更新。原report.md保留为历史科学报告；本说明记录后续接口变化。新的四态目标与潜机制检验另见LH264目录，不覆盖原三态结果。
