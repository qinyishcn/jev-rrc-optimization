# RRC 来源审计与证据边界

审计日期：2026-09-28。结论：公开数据适合验证 **LTE RRC 文本解析、配置提取和消息模板集成**，不足以训练或验证配置优化收益。没有 DRX 配置样本，没有业务包时延、负载、丢包或配置干预后结果标签；本项目新增的 DRX 场景与时延模型不能称为从这份数据校准、学习或实测得到。

## 来源与版本

| 来源 | 锁定版本 | 核验结果 |
|---|---|---|
| [EEzim/RRC 数据集](https://huggingface.co/datasets/EEzim/RRC/tree/e473ea8b9891f608afb7d9ad89c412e2dda27e18) | `e473ea8b9891f608afb7d9ad89c412e2dda27e18` | 已下载全部 3 个文件；Parquet 哈希符合 HF LFS 元数据 |
| [nrRRC_Simulator](https://github.com/EE-zim/nrRRC_Simulator/tree/228ad4bc7ebce1093e215a9285ee126eb862ee95) | `228ad4bc7ebce1093e215a9285ee126eb862ee95` | 静态阅读及轻量功能测试；未运行完整 srsRAN 无线栈 |
| [论文](https://arxiv.org/pdf/2505.16821v5) | v5，2026-01-15，16 页 | 使用当前链接对应的 v5；不是最早版本 |

数据文件 `demo.parquet` 为 21,429 字节，SHA256 为 `530084af5436b544c4ab3c9e0090e503080ba403cc363c26d138b637c4091ccf`。与上游 GitHub 的 `demo.parquet` 逐字节相同。论文 PDF 为 1,715,200 字节，SHA256 为 `d6825b0f25e6715a676825e54deed2a5f67f0d12b833c5c38a4b6ca3ece6c9a0`。其他文件哈希及机器可读结果见 [rrc_audit.json](../artifacts/rrc_audit.json)。

## 数据到底包含什么

实际只有 **16 行、4 列**：`Q_Timestamp`/`A_Timestamp` 为浮点秒，`Q_Content`/`A_Content` 为协议文本。无空值、无完全重复行。32 个问答文本单元均包含 LTE 协议标识；其中可能合并连续同方向的多条消息，因此消息出现次数不等于行数。内容涉及连接请求/建立、NAS 转移、安全模式、能力信息、重配置、释放及寻呼。

数据卡将规模写为 `10K<n<100K`，并给出 `timestamp`、`direction` 字段说明；均与本次实际文件不符。应以下载文件为准。8 项白名单配置在样本中各出现 3 次：

| 字段 | 观察值 |
|---|---|
| `t-Reordering` | `ms45` |
| `periodicBSR-Timer` | `sf20` |
| `retxBSR-Timer` | `sf320` |
| `timeAlignmentTimerDedicated` | `infinity` |
| `prioritisedBitRate` | `infinity` |
| `bucketSizeDuration` | `ms100` |
| `logicalChannelGroup` | `2` |
| `priority` | `13` |

此表是文本中出现的配置，不是可直接套用到所有承载的全局参数。未观察到 `drx-Config`、`onDurationTimer`、长短 DRX 周期、A3 偏移或 TTT 配置值。

`A_Timestamp-Q_Timestamp` 中位数约 **6.382 ms**，最大值约 **39.447 s**。这只是被配对消息的墙钟间隔；上游按同方向分组再配对，既没有 UE/session 因果关联键，也没有逐包收发标识，不能解释成无线包时延、业务端到端时延、LLM 推理时延或“调整某个参数后的收益”。

## 上游模拟器的实际能力

[README](https://github.com/EE-zim/nrRRC_Simulator/blob/228ad4bc7ebce1093e215a9285ee126eb862ee95/README.md) 的标题使用 5G，但其安装路径是 srsRAN_4G，运行依赖 Linux、EPC/eNB/srsUE、ZeroMQ、网络命名空间和固定 `/home/...` 路径。Python 部分主要是编排、移动性辅助、日志提取与展示，不能仅凭项目名视为完整 NR 包级模拟器。

- [rrc_utils.py](https://github.com/EE-zim/nrRRC_Simulator/blob/228ad4bc7ebce1093e215a9285ee126eb862ee95/rrc_utils.py#L76) 把同方向消息合并，并用相邻 UL/DL 组形成 QA；没有配置优化奖励模型。
- [channel_models.py](https://github.com/EE-zim/nrRRC_Simulator/blob/228ad4bc7ebce1093e215a9285ee126eb862ee95/srsRAN_5G/srsRAN_5G/channel_models.py#L42) 使用路径损耗和随机衰落；外部仿真接口仍为占位实现。
- [UE.connect_to_gnb](https://github.com/EE-zim/nrRRC_Simulator/blob/228ad4bc7ebce1093e215a9285ee126eb862ee95/srsRAN_5G/srsRAN_5G/enhanced_ue_mobility_controller_v2.py#L271) 只更新 Python 对象和成员列表；`update_connections` 使用固定 3 dB 偏移及 -105/-110 dBm 阈值。不能从这段实现声称已向无线栈执行真实切换或完成 TTT 优化。
- [RealTimeMetricsCollector._get_latency](https://github.com/EE-zim/nrRRC_Simulator/blob/228ad4bc7ebce1093e215a9285ee126eb862ee95/srsRAN_5G/srsRAN_5G/enhanced_performance_metrics_collector.py#L1254) 返回 `random.uniform(0, 100)`；该文件还缺少对应 `random` 导入。其他采集类可从日志匹配延迟数字，但读取标签不等于证实数字来自有效包测量。仓库自带图表与统计文件不计入本项目实测。

本机轻量测试：UTF-8 模式下，上游解析器读到 37 条消息，产生 16 对 QA；合成 UL/DL 配对测试通过；固定随机种子时，简化信道的远端 RSRP 低于近端。`rrc_toolkit.py --help` 退出码 1，报缺少 `pcap`。默认 Windows GBK 模式读取示例日志失败，使用 `python -X utf8` 可绕过编码问题。这些结果只证明相应 Python 核心函数可运行，**没有完成完整无线栈部署，也没有测得真实网络时延**。

## 论文能支持的结论

v5 的摘要、§III–IV 和表 IV/V/X/XII 报告协议消息生成质量及推理耗时；NR 与 LTE 主实验语料均为私有数据，公开 16 行不是论文约 30k NR 对及 4.8k LTE turns 的复现集。0.97/61% 是语义相似度及其相对改善；20–30% 是 INT4 相对 FP16 的推理时间改善，不是相对传统 RRC 配置的业务时延改善。论文 §IV.C 明确没有微调配置达到低于 100 ms 的中位推理耗时，完整协议输出常在秒级。上述论文指标不能作为本项目“优化成功”的测量值。[论文 v5](https://arxiv.org/pdf/2505.16821v5)

## 新增 DRX 候选的标准取值核验

独立对照 [ETSI TS 136 331 V10.21.0 / 3GPP TS 36.331，§6.3.2 MAC-MainConfig，印刷页 177–178](https://www.etsi.org/deliver/etsi_ts/136300_136399/136331/10.21.00_60/ts_136331v102100p.pdf)：`off` 对应 `DRX-Config release`；周期/开启时长候选 `10/8, 10/4, 10/2, 20/8, 20/4, 32/8, 40/4, 80/4` 的周期和 on-duration 均属于允许枚举。周期单位为子帧，on-duration 单位为 **PDCCH 子帧**。若简化为毫秒，应显式采用每毫秒可监控的 LTE FDD 假设。

这仅是两个字段的取值检查；完整 `setup` 还要求 inactivity/retransmission timer 和合法 start offset（0 至周期减 1）。需要声明未模拟的 Active Time 延长、HARQ、短 DRX、TDD、调度和无线误码影响；通过这个检查不等于完整 ASN.1 编解码、协议一致性或真实设备验证。候选是项目新增，数据集中没有 DRX 证据。

## 可执行的有限集成路径

1. 从公开 QA 中提取消息类型和白名单配置，为 Decider 提供经脱敏的上下文；先验证选项结构、参数范围、不可用场景拒绝及返回值可解析。
2. 独立建立透明的 DRX 等待/排队场景模型，将业务负载、截止时间、功耗代理和所有假设写入输入。其结果应称为“指定模型下的仿真收益”，不叫公开数据实测或网络校准结果。
3. 用同一批未参与选择的随机流量，比较固定配置、规则自适应、搜索最优值与 Decider 选择；同时保留 always-on 时延下界及功耗代价，避免只挑弱基线。
4. 要声称实际时延收益，需另行取得配置干预及逐包结果关联的测试床/可信包级模拟器数据，包含负载、服务类别、radio/session 状态、切换成本和失败样本。

## 复现、许可与发布范围

```powershell
python -X utf8 scripts/audit_rrc_sources.py
python -X utf8 scripts/audit_rrc_sources.py --offline
```

脚本使用本机已有 pandas/pyarrow，没有全局安装。若 Python 的 arXiv TLS 信任链失败，不降低 TLS 验证；可用 Windows 系统信任链的 `Invoke-WebRequest` 单独下载 PDF 后重跑。此次 PDF 已通过该方式下载并核查为 16 页。

HF 数据卡声明 Apache 2.0，但没有独立 LICENSE 文件；GitHub 快照未找到 LICENSE/COPYING，不据此推定其源码可重新许可。公开输出只含链接、哈希、聚合配置和自主编写脚本/报告；`external/` 与 `data/rrc/` 的上游源码、PDF 和原始 trace 保留在本地。原始 trace 含终端标识及 NAS 载荷，不嵌入公开报告。`artifacts/rrc_audit.json` 使用配置白名单，不包含原始消息正文、身份值或 NAS 载荷。
