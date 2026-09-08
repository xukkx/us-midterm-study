# 需完整研究资产的集成测试

这8个文件保留首次公开版的原测试，已从默认单元测试目录移出。它们目前不能在这个公开包独立运行；不是已通过或自动跳过的测试。

- `test_benchmark.py`：需要benchmark.py及其基准配置。
- `test_real_benchmark.py`：需要real_benchmark.py、历史账本与来源配置。
- `test_ingest.py`、`test_presidential_ingest.py`：需要原研究runner、数据与冻结来源清单。
- `test_fec_ingest.py`：需要FEC年度源文件、清单及校验配置。
- `test_senate_balancing_preregister.py`、`test_senate_joint_benchmark.py`、`test_senate_m0_benchmark.py`：需要各自的预注册配置、runner及冻结账本。

具有完整原研究资产的环境仍使用原来的tests目录运行这些断言。公开包的可独立执行范围、实证输入和CI命令见`../public/README.md`。集成材料尚未整理为可公开重建的下载包，不宣称已经全链复现历史研究。
