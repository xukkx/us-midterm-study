# Pew公开基准与CES的可比性

Pew报告给出的公开基准是：其纵向加权的2020总统大选投票参与者中，68%在2022年中期选举再次参与。分母是Pew纵向分析中具有2020投票参与记录的合格选民；来源没有给出该比例的确切人数分母。该数字用于说明跨期总体参与变化。

Pew用自报投票与商业选民档案匹配验证参与。未自报投票者视为未投票；没有在三个商业档案中找到记录者通常也视为未投票，犹他州因登记和投票历史可选择保密而有例外。纵向分析使用 `WEIGHT_W78_W117_VALIDATEDVOTE`（longitudinal special weight）。

可比较之处是跨期总体参与变化。不可比较之处是职位、候选选择和总体权重体系：2020是总统票，2022是众议院票；Pew是纵向加权验证样本，CES主表是另一总体。这里不把两种选票相减，不推断众议院票转换，也不使用PID结果。Pew公开文件还删除了部分纵向变量以保护隐私，因此公开复现可能与原报告略有差异。

官方来源：[验证2022投票者](https://www.pewresearch.org/decoded/2024/10/31/validating-2022-voters-in-pew-research-centers-survey-data/)、[2022中期选举报告](https://www.pewresearch.org/politics/2023/07/12/republican-gains-in-2022-midterms-driven-mostly-by-turnout-advantage/)、[方法说明](https://www.pewresearch.org/politics/2023/07/12/validated-voters-2022-methodology/)。
