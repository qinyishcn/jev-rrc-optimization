# 下一步：在 NR 系统中验证 Decider 的 DRX 配置价值

**结论先行。** 当前 [LTE 合成队列实验](report.md)没有证明 Decider 优于确定性自适应规则：原始选择有 36/90 个超标场景，筛选后的选择虽无超标，却比规则使用更高的配置接收占空比。下一步应把问题固定为**连接态 NR 下行 DRX 配置**，先验证配置确实进入 UE，再在相同业务与无线条件下比较实际包时延和 UE 能耗。LTE 的 16 条公开 RRC 记录只提供协议上下文，不提供 DRX 干预结果；[论文 2505.16821v5](https://arxiv.org/pdf/2505.16821v5)考察的是 RRC 消息仿真，不能作为配置优化收益证据。

## 平台决定与先决门槛

**首选 [srsRAN Project](https://github.com/srsran/srsRAN_Project) 25.04 或更新的固定版本 + [Open5GS](https://github.com/open5gs/open5gs) + 已验证可接入的 5G UE。** srsRAN 的[25.04 发布说明](https://docs.srsran.com/projects/project/en/latest/general/source/5_release_notes.html)明确列出 DRX；[配置参考](https://docs.srsran.com/projects/project/en/latest/user_manuals/source/config_ref.html)公开 `on_duration_timer`、`inactivity_timer`、上下行重传定时器和 `long_cycle`，其中 `long_cycle: 0` 关闭 DRX。这是“gNB 支持配置”的上游证据，**不是本项目已经测得 UE 实际休眠或省电的证据**。实验先用静态配置逐轮接入；运行中按 UE 动态切换是否可用，尚须代码与 RRC 消息验证。不要把 E2/KPM 或 xApp 接通当成 DRX 动态控制已接通：[官方 E2 教程](https://docs.srsran.com/projects/project/en/latest/tutorials/source/near-rt-ric/source/)描述的 RC 能力有限，未给出 DRX 控制路径。

本机 Windows/RTX 3070 可继续跑 Decider 离线推理和日志分析；[srsRAN 要求 Linux，推荐 Ubuntu 22.04+](https://docs.srsran.com/projects/project/en/latest/user_manuals/source/installation.html)。WSL/Linux 可完成构建与无射频预检，不能据此认定 Windows 主机具备稳定的实时空口能力。真正端到端试验需要 Linux gNB、USRP 或受支持 RU、5G 核心、SIM/UE；[官方运行要求](https://docs.srsran.com/projects/project/en/latest/user_manuals/source/running.html)也建议 COTS UE 使用外部参考时钟。[已测 UE/频段清单](https://docs.srsran.com/projects/project/en/latest/knowledge_base/source/cots_ues/source/index.html)应在采购前核对。无射频时，[gNB testmode](https://docs.srsran.com/projects/project/en/latest/tutorials/source/testmode/source/index.html)仅能压测调度路径，不能提供真实 UE 的 DRX 时延或电流；[srsUE/ZeroMQ 教程](https://docs.srsran.com/projects/project/en/latest/tutorials/source/srsUE/source/)虽可用于初始接入排错，不能在确认其 UE 侧 DRX 行为前充当能耗验证。

备选的 [5G-LENA NR-v5.1/ns-3.48](https://cttc-lena.gitlab.io/nr/html/)适合在多 UE、[38.901 信道与 XR 业务模型](https://cttc-lena.gitlab.io/nr/html/features.html)下复核调度/负载敏感性；其公开功能表没有列明连接态 DRX，也没有在此核实到可直接使用的 DRX KPI。若选这条路，先检查版本源码、补实现并用手算轨迹验证 DRX Active Time 与调度门控，之后才报告 DRX 增益。ns-3 的 `DrxConfig_s` [字段定义](https://www.nsnam.org/docs/release/3.41/doxygen/d5/d61/structns3_1_1_drx_config__s.html)本身不证明运行逻辑。5G-LENA 的 NR-U “duty cycling”是信道接入，不等于 UE 连接态 DRX。

## 可复现业务输入及其证据边界

| 输入 | 可用字段与具体用法 | 局限 |
|---|---|---|
| [5G-LENA 官方 3GPP XR 业务生成器](https://cttc-lena.gitlab.io/nr/html/cttc-nr-traffic-3gpp-xr_8cc_source.html) | 固定版本与 RNG stream，选择 VR/AR/云游戏的场景视频、音频/数据、姿态/控制流；记录应用生成时刻、包长、方向、流 ID、帧率/码率和种子。其 [TrafficGenerator `Tx` trace](https://cttc-lena.gitlab.io/nr/html/classns3_1_1_traffic_generator.html)可导出逐包到达序列，再由 srsRAN 试验的 UDP 发送器按时间回放。 | 这是按 [3GPP XR 模型实现的生成流](https://cttc-lena.gitlab.io/nr/html/md__2builds_2cttc-lena_2nr_2_r_e_l_e_a_s_e___n_o_t_e_s.html)，不是实测 UE 业务。生成器本身也不包含 DRX/功耗干预标签；回放后发包偏差须实测并保存。 |
| [UFSCar LERIS AR/云游戏公开抓包与特征](https://github.com/dcomp-leris/VR-AR-CG-network-telemetry) | 作者公开 AR 视频流的 PCAP 及提取 CSV，列出 `PS`（包字节数）、`IPI`（包间隔）、方向、协议、帧大小 `FS` 和帧间隔 `IFI`；云游戏部分含 5G/光纤实验。优先从原始 PCAP 提取发送端逐包时间戳/长度，选下行流用于外部流量形状复核。项目提供 [BSD-3-Clause 许可证](https://github.com/dcomp-leris/VR-AR-CG-network-telemetry/blob/main/LICENSE)。 | CSV 特征不能保证还原原始包的完整时序；抓包位置、Wi-Fi/公网排队会混入到达间隔。下载后需核对 PCAP 可用性、时间戳精度、方向和内容许可，脱敏 IP；这不是 DRX 效果数据。 |
| [3GPP TS 22.104 §5.2 工业周期确定性通信](https://www.etsi.org/deliver/etsi_ts/122100_122199/122104/19.02.00_60/ts_122104v190200p.pdf) | 从标准表选择一行，显式记录传输间隔、消息大小、目标时延、可靠性和 survival time；生成周期消息并对相位/有限抖动做独立种子扫描。这比沿用当前手选的 5 ms 截止值更可溯源。 | 它是业务要求与生成参数，不是公开实测逐包 trace；不能据此声称已经达到相应可靠性/可用性，也不能用几十轮实验验证极高可靠性等级。 |

优先把**同一份已冻结的逐包清单**（`flow_id, direction, scheduled_send_ns, payload_bytes, deadline_ns, seed, source_revision`）输入全部策略；清单可由前两项生成/提取，并用第三项定义工业流。每轮额外保存实际发包时间，比较预定与实发偏差。训练/校准与最终测试用不同文件和种子，按时间段或应用/视频源分组，避免连续帧跨集合泄漏。上述公开来源及仓库现有 EEzim/RRC 样本中，**没有核实到同时包含 RRC/DRX 配置干预、逐包 UE 时延和同一 UE 能耗的配对公开数据集**；收益标签只能通过后续受控试验新采集，不能从业务输入或网络带宽 trace 推断。

## 按门槛推进的实验

| 阶段 | 具体工作与可复核产物 | 继续条件 |
|---|---|---|
| 0. 环境与配置预检 | 固定 srsRAN/Open5GS/UE/固件版本和哈希；Linux 上编译、跑上游相关测试；分别启动 `long_cycle: 0` 与 10/20/40 ms 的合法配置，核对配置解析、gNB 日志及解码后的 RRCReconfiguration/UE 确认。记录是否必须重连才生效。 | UE 确认收到所选参数；否则先修配置链路，不运行性能比较。 |
| 1. 单 UE 静态对照 | 屏蔽箱或有线衰减连接下，固定频段、带宽、调度器与功率；下行发送带序号和时间戳的周期/突发 UDP 流。每轮先应用一种配置并确认，再测每包到达、丢失、超时、MAC/RLC 重传及 UE 电流。 | 能重复观察配置变化引起的 UE 活跃/睡眠行为；否则只报告 IP/RRC 指标，不宣称省电。 |
| 2. 鲁棒性与外推 | 低/中/高负载、平稳/突发流量、好/弱信道、1/多 UE；每个场景用新流量种子与随机化配置顺序，至少 30 个独立轮次作为初始目标，并按置信区间决定是否增加轮次。多 UE 需实际 UE 或已核验可用的仿真路径。 | 每种方法使用同一场景分布，记录全部失败/重连轮次；不能只挑成功接入样本。 |
| 3. 动态控制（仅在确有需求时） | 若静态配置显示可验证收益，再实现受限候选集的运行时重配置接口；逐次记录“决策请求→模型输出→RRCReconfiguration 发送→Complete→首次按新配置调度”的时间与失败。 | 每阶段有可观测时间戳、回滚方案和 UE 一致性检查；否则结论限于业务建立前配置。 |

候选集先保留小范围的 `off`、`10/8`、`10/4`、`20/8`、`20/4`、`40/4`（毫秒；以所固定 srsRAN 版本实际接受的 NR 值为准），固定其他 DRX 定时器并公开其值；再单独研究 inactivity/重传定时器，避免一次改变多个因素。NR 的允许参数与 Active Time 语义分别以 [TS 38.331](https://www.etsi.org/deliver/etsi_ts/138300_138399/138331/18.08.00_60/ts_138331v180800p.pdf) 和 [TS 38.321 §5.7](https://www.etsi.org/deliver/etsi_ts/138300_138399/138321/17.13.00_60/ts_138321v171300p.pdf)为准，不能直接把本仓库 LTE 配置片段发送给 NR gNB。

## 公平比较、指标与判定

比较 `off`、运营式固定配置、校准集按业务选的固定配置、确定性自适应规则、`guard_only`、Decider 原始选择、Decider + 同一个 guard。候选集、观测特征与约束完全相同；所有可调基线只在训练/校准轮次调参，提示词和 guard 在盲测前冻结。Decider 看不到未来包到达、种子、候选实测结果或标签。事后最优只作不可部署上界。如果 `guard_only` 在满足相同时延约束时比 Decider + guard 耗能更低，就不能把 guard 的贡献归给模型。模型当前约 186 ms 暖态推理只适于提前配置或慢速控制，不计作 5/10/20 ms 逐包控制能力。

主指标是**真实 UE 每有效交付比特的能量**及独立测量窗口的电流积分；同时报告包级单向时延 P50/P95/P99、超期率、丢包、IP goodput、配置失败率。单向时延需 UE 与发送端校时；否则报告 RTT 并明确其含义。每包 ID 用于识别丢包，不能把未送达包从超期分母删除。UE 电流最好由外部供电/电流仪测量并控制屏幕、后台服务、充电状态与射频条件；仅有 gNB 占空比或调度日志时，指标只能命名为代理值。[srsRAN 输出说明](https://docs.srsran.com/projects/project/en/latest/user_manuals/source/outputs.html)提供 MAC/RLC PCAP 与 JSON/RRC 指标入口，但应用层逐包时延和 UE 电流需要另行采集。RRC 信令延迟与配置生效延迟独立报告，避免隐藏切换成本。

预先设定每业务的时延/超期约束；5/10/20 ms 沿用旧实验时只能称**本研究目标**，先用 `off` 测其在实际网络中是否可达。只有在盲测中约束成立、且相对最强可部署基线的能量差的独立轮次置信区间仍支持节省，才称“该测试条件下有增益”。按业务、信道、负载分别报告成对差值和独立轮次 bootstrap 区间；UE/轮次为独立单位，不能把同轮数千包当作数千个独立复现。若全部方法超期，报告不可行区域而不改阈值追求正结果。

**工作量估计（待环境核对）：**已有 Ubuntu 与 RF/UE 时，阶段 0 约 2–4 天，单 UE 仪器化与阶段 1 约 1–2 周，阶段 2 约 1–2 周；动态控制是额外研发，不计入首轮。只有当前 Windows/RTX 3070 且无 RF/UE 时，可完成阶段 0 的软件预检及实验脚本设计，无法产出真实 UE 能耗或空口时延结论。公开材料保存版本、配置、聚合指标和脱敏日志；公开上游代码或原始数据前分别核对 [srsRAN](https://github.com/srsran/srsRAN_Project/blob/main/LICENSE)、[Open5GS](https://github.com/open5gs/open5gs/blob/main/LICENSE) 及 UE/流量数据许可。
