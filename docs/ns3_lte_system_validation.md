# LTE 协议栈中的 RRC A3 配置优化：系统验证与模型负结果

2026-10-01。此报告接续 [DRX 合成队列实验](report_v2.md)。先前仿真器不能计算不同 RRC 配置下的真实协议栈通信性能。本次改用 **ns-3 3.46 的 LTE/EPC/X2 全栈**，让同一移动 UE 和下行 UDP 流在不同 RRC Event A3 切换配置下运行，记录应用层逐包时延、丢失、20 ms 超期和 RRC 切换事件。这是协议栈软件仿真，**不是 5G NR、DRX、真实射频或 UE 能耗实测**。新用例是紧时延移动业务的切换配置，因 ns-3 LTE 原生支持 A3；不能将本结果直接外推到原 DRX 问题。

## 结果与对照

五档候选配置是 `(A3 hysteresis dB, time-to-trigger ms)`：`(0,0)`、`(1,80)`、`(2,160)`、`(3,256)`、`(6,320)`。Hysteresis 表示邻区 RSRP 高于服务小区所需的额外余量，TTT 表示此条件持续多久才触发报告；数值越大通常越保守。[ns-3 A3 说明](https://www.nsnam.org/docs/models/html/lte-user.html)与[3.46 头文件中的设置示例](https://gitlab.com/nsnam/ns-3-dev/-/blob/ns-3.46/src/lte/model/a3-rsrp-handover-algorithm.h)说明应在安装 eNB 设备前设置这两个属性；`(3,256)` 是 ns-3 A3 默认值。

先用随机运行号 1、2 的 12 种场景选出最佳全局固定配置 `(0,0)`，并冻结一个描述符规则：**仅在边界往返、速度不超过 8 m/s 且 UDP 间隔不超过 1 ms 时选 `(1,80)`，其余选 `(0,0)`**。然后用未参与选择的运行号 11–15 复核，同一场景/种子对所有配置完全配对。原版 Decider 和 Qwen3.5-2B-Base 各对 12 个场景描述符推理一次，选项在五个种子上复用；其提示词实验属于探索性对照，不能当作重新训练后的盲测。离线事后最优使用了真实结果，仅是候选集内上界。

| 方法 | 20 ms 超期或丢失包 / 891,000 | 比例 | 丢失包 | RRC 切换开始次数 | 已收到包的场景 P99 均值 |
|---|---:|---:|---:|---:|---:|
| A3 默认 `(3,256)` | 49,869 | 5.597% | 3,125 | 30 | 67.52 ms |
| 校准后最强全局固定 `(0,0)` | 4,566 | 0.512% | 3,166 | 350 | 6.75 ms |
| Qwen3.5-2B-Base，零样例 | 4,566 | 0.512% | 3,166 | 350 | 6.75 ms |
| A3 专用 LoRA Decider | 4,566 | 0.512% | 3,166 | 350 | 6.75 ms |
| 描述符规则 | **3,131** | **0.351%** | **2,211** | 290 | **6.08 ms** |
| 候选集事后最优 | 3,131 | 0.351% | 2,211 | 182 | 5.93 ms |
| 未适配 Decider 2B | 37,939 | 4.258% | 6,053 | 110 | 47.64 ms |

规则相对默认配置减少 **93.72%** 的超期或丢失包；相对校准后最强固定配置减少 **31.43%**。这些是选定场景网格内的包数比例变化，不是所有网络的预期收益。规则在本次 60 组场景/种子上达到五档候选中的最少超期包数，因此这组条件**没有可归因于 Decider 的额外超期率增益空间**。未适配 Decider 固定选择 `(2,160)`，比简单固定 `(0,0)` 更差；Qwen 与 A3 专用 LoRA Decider 都固定选择 `(0,0)`，与强固定基线完全相同。三种模型输出都没有识别低速边界往返时的例外。原版 Decider 的 12 次预热后选择墙钟中位数为 **205.62 ms**，Qwen 为 **978.50 ms**，Decider 快约 4.76 倍；模型决策时间未计入业务包时延，后续外推批次的绝对耗时随本机负载变化。Qwen 的第一个零样例提示词只生成换行，改用补全前缀 `Answer: P` 后得到 12/12 有效选项；报告的时间和性能来自该最终提示词，故不把这次格式调整伪装为未调整过的模型盲测。[完整 Decider 输入/概率](../artifacts/system_validation/decider_a3_base.json)与[Qwen 提示词/原文](../artifacts/system_validation/qwen_a3_base.json)保留了证据。

## 领域适配与跨几何外推

为检验“原模型只是没学过 A3”这一解释，另用 **32 个不与评估场景重合的描述符**、每个两次 ns-3 随机运行、五档配置，共 **320 次仿真**生成标签：先最小化超期或丢失包，再以丢失和切换次数破同分。标签为 18 个 `(0,0)`、14 个 `(1,80)`。[训练程序](../system_validation/train_decider_a3.py)以 208,896 个可训练 LoRA 参数、两轮、学习率 `2e-4` 训练 Decider；RTX 3070 耗时 **428.28 s**，原网格独立验证标签交叉熵从 **2.089 降至 0.562**。[训练记录与权重哈希](../artifacts/system_validation/a3_train_result.json)可复核。**但适配模型在原网格 12 个、第一外推 20 个、最终新几何 15 个描述符上均只选择 `(0,0)`**；训练损失下降没有转化为自适应配置收益。单纯 Choice 温度缩放不会改变最大概率选项；[前次 DRX 温度实验](report_v2.md)也直接验证了这一点。要让概率门控改变选择，需额外校准规则，其贡献不能记为模型独有。

第一外推集改变小区间距为 200/450 m、穿越速度及往返周期：20 种场景 × 3 个新运行号 × 5 配置 = **300 次仿真**。先冻结的速度规则超期率为 **0.548%**，五档事后上界 **0.393%**，说明原规则不是普遍最优。查看这组结果后构造第二版传统规则：仅在高负载边界往返且“半周期位移 / 小区间距”不超过 **0.033** 时选 `(1,80)`，其余 `(0,0)`。这个阈值来自第一外推集，**不能用该集上的表现宣称盲测增益**。

随后固定第二版规则，用新的间距 250/375/550 m、速度 5/8/11/15/20 m/s、反向周期 2.3 s 和运行号 41–45 测试。15 个未见过的描述符 × 5 次运行 × 5 配置 = **375 次完整仿真**，全部是 20 ms 截止的高负载业务。

| 方法 | 第一外推集：超期或丢失 / 1,113,000 | 最终新几何集：超期或丢失 / 1,725,000 |
|---|---:|---:|
| A3 默认 `(3,256)` | 40,795（3.665%） | 56,497（3.275%） |
| 校准固定 `(0,0)` | 8,394（0.754%） | 18,071（1.048%） |
| 未适配 Decider | 36,288（3.260%） | 65,494（3.797%） |
| A3 LoRA Decider | 8,394（0.754%） | 18,071（1.048%） |
| Qwen3.5-2B-Base | 8,394（0.754%） | 18,071（1.048%） |
| 速度规则 v1 | 6,099（0.548%） | 12,205（0.708%） |
| 几何归一化规则 v2 | **4,377（0.393%）**¹ | **10,136（0.588%）** |
| 候选集事后最优 | 4,377（0.393%） | 9,495（0.550%） |

¹ v2 规则使用了第一外推集调阈值，该列是拟合检查；**最终新几何列**才是冻结后的迁移检查。最终集上 v2 比最强固定方案少 **43.91%** 的超期或丢失包，比 A3 默认少 **82.06%**；仍比事后上界多 **641 包**，主要来自一个 `375 m / 11 m/s` 场景。这证明当前候选集仍有约 0.037 个百分点的超期率空间，但**已测 Decider 及其 LoRA 未利用它**。此处的“没有模型增益”只针对这些平台假设、模型版本、训练集和配置候选；不构成所有无线网络或所有 Jev 类模型的普遍不可能性证明。第一外推和新几何的[逐配置数据](../artifacts/system_validation/fresh_geometry.jsonl)、[最终汇总](../artifacts/system_validation/fresh_geometry_summary.json)与[适配模型原文选择](../artifacts/system_validation/decider_a3_adapted_fresh.json)已公开。

## 两个具体紧时延用例

输入是**会话建立前可获得的场景描述**，不含随机种子、未来到达序列或任何候选结果。两基站中心分别在 `x=-150 m`、`x=+150 m`，UE 初始接入左侧基站；EPC 到远端发送机之间有 1 ms 有线回传。所有业务从仿真第 1 s 开始发送，截止到结束时刻，包大小包含 12 字节序号/时间戳。每种方案只在业务开始前选一次 A3 配置，不逐包推理，也没有在运行中变更 RRC 参数。以下均是留出随机运行号 11 的实测行；每项完整指标在[逐配置 JSONL](../artifacts/system_validation/holdout.jsonl)和[按方法汇总](../artifacts/system_validation/holdout_summary.json)。

**低速边界往返，高负载：** `trajectory=oscillate`，初始 `x=-8 m`，速度 `8 m/s`，每 `2 s` 反向，两个 eNB 间距 `300 m`，仿真 `24 s`，下行 UDP 每 `1 ms` 发 `1,200 B`，20 ms 截止；23 s 业务时间共发送 23,000 包。`trajectory`、位置、速度和反向周期用于推断 UE 是否频繁跨越小区边界；发包间隔与大小决定业务负载；截止时间决定超期判据。Decider 收到上述字段、A3 含义、五个文本选项及“最小化超期或丢失比例”的问题；未适配版实际输出 `(2,160)`，LoRA 适配版及 Qwen 输出 `(0,0)`，规则输出 `(1,80)`，默认方法为 `(3,256)`。

| A3 配置 | 收到 / 23,000 | 丢失 | 已收超期 | 总超期或丢失 | 均值 / P95 / P99 时延 | 切换次数 |
|---|---:|---:|---:|---:|---:|---:|
| `(0,0)`，Qwen/适配 Decider/固定 | 22,809 | 191 | 96 | 287 | 5.17 / 5 / 13 ms | 12 |
| `(1,80)`，规则 | 23,000 | 0 | 0 | **0** | 5.00 / 5 / 5 ms | 0 |
| `(2,160)`，Decider | 23,000 | 0 | 0 | **0** | 5.00 / 5 / 5 ms | 0 |
| `(3,256)`，默认 | 23,000 | 0 | 0 | **0** | 5.00 / 5 / 5 ms | 0 |
| `(6,320)` | 23,000 | 0 | 0 | **0** | 5.00 / 5 / 5 ms | 0 |

此用例表明更激进切换不总是好；但 Decider、默认及其他保守配置在该用例上也为零超期，不能据此声称规则或模型独占收益。

**单向穿越，高负载：** 初始 `x=-120 m`，速度 `15 m/s` 一直向右，仿真 `32 s`，每 `1 ms` 发 `1,200 B`，31 s 业务时间共 31,000 包。其余网络和 20 ms 截止同上。未适配 Decider 仍输出 `(2,160)`，适配版、Qwen 与规则输出 `(0,0)`。`(0,0)` 仅 **23** 个超期或丢失包，P99 **5 ms**，首次切换开始于 **8417 ms**；未适配 Decider 的 `(2,160)` 为 **619** 包、P99 **69 ms**、首次切换 **9777 ms**；默认 `(3,256)` 为 **1224** 包、P99 **131.75 ms**、首次切换 **10473 ms**。这里及时切换改善了弱服务小区下的时延。表中 P99 只对已收到包计算，主指标始终把丢包列入分母和失败数。

## 仿真频率、复现与证据边界

初始设计为 12 种场景：三档速度的单向穿越、三档速度/周期的边界往返，每种搭配 `10 ms/200 B` 和 `1 ms/1200 B` 两档下行业务。每场景先探索两次运行号、后复核五次运行号；每个场景/运行号对五档配置分别运行，因此初始部分 **120 + 300 = 420 次完整 LTE/EPC 仿真**。之后增加 300 次跨几何外推、320 次 LoRA 训练标签和 375 次最终新几何检验，**总计 1415 次仿真**。业务持续时间均为 24 或 32 s，`10 ms` 场景每轮发送 2300/3100 包，`1 ms` 场景发送 23000/31000 包。初始留出 300 次运行的单次 CPU 墙钟中位数约 **0.819 s**，并非通信时延。模型对每种场景只推理一次，同场景各随机运行号共享预先选出的配置；没有逐包或运行中推理。Decider 与 Qwen 的推理墙钟是本机 RTX 3070 上的软件时间，不是空口控制生效时间；原网格的 205.62/978.50 ms 只是同批实测值，后续本机负载变化使绝对时间增加约数倍，但 Decider 仍较快。

环境为 Ubuntu 26.04 WSL2 的 `ns3`/`libns3-dev` Debian 包 **3.46-2**、GCC **15.2.0**；[源程序](../system_validation/ns3_lte_handover.cc) SHA256 `ed1607a06002999a64a4583849b992e2d3b373ae71fb2b515414b7a8e2805fa6`。安装 `libns3-dev ns3 libxml2-dev libsqlite3-dev libgsl-dev` 后，在 WSL 执行：

```bash
g++ -std=c++20 -O2 system_validation/ns3_lte_handover.cc -o rrc-handover \
  $(pkg-config --cflags --libs ns3-lte ns3-applications ns3-internet ns3-mobility ns3-point-to-point)
python3 system_validation/run_sweep.py --binary ./rrc-handover \
  --source system_validation/ns3_lte_handover.cc \
  --output artifacts/system_validation/exploratory.jsonl --runs 1,2
python3 system_validation/run_sweep.py --binary ./rrc-handover \
  --source system_validation/ns3_lte_handover.cc \
  --output artifacts/system_validation/holdout.jsonl --runs 11,12,13,14,15
python3 system_validation/run_sweep.py --binary ./rrc-handover \
  --source system_validation/ns3_lte_handover.cc \
  --output artifacts/system_validation/generalization.jsonl --runs 21,22,23 --suite generalization
python3 system_validation/run_sweep.py --binary ./rrc-handover \
  --source system_validation/ns3_lte_handover.cc \
  --output artifacts/system_validation/adaptation_labels.jsonl --runs 31,32 --suite adaptation
python3 system_validation/run_sweep.py --binary ./rrc-handover \
  --source system_validation/ns3_lte_handover.cc \
  --output artifacts/system_validation/fresh_geometry.jsonl --runs 41,42,43,44,45 --suite fresh_geometry
python3 system_validation/verify_results.py
```

Windows 上的本地模型脚本是 `system_validation/decider_a3.py`、`system_validation/qwen_a3.py` 和 `system_validation/train_decider_a3.py`，使用仓库旧实验已校验的 [Mapika Decider 权重](decider_adaptation.md)和 [Qwen3.5-2B-Base 权重](qwen_baseline.md)。`artifacts/system_validation/*.jsonl` 提供逐场景/逐配置原始统计，模型 JSON 保留实际完整输入和选择，分析脚本 `analyze_sweep.py` 只复用这些记录。校验通过：每个场景/运行号恰有五档结果、源码哈希一致、发送数等于收到数加丢失数、没有重复序号、超期加丢失等于主指标、无记录到的切换失败；这不等于已验证所有真实无线异常。官方 [LTE 模型文档](https://www.nsnam.org/docs/models/html/lte-user.html)和 [上游 X2 切换示例](https://gitlab.com/nsnam/ns-3-dev/-/blob/ns-3.46/src/lte/examples/lena-x2-handover.cc)用于核对 API 和拓扑；本仓库实验代码是独立实现。

## 当前结论与下一轮实验

本仿真已能比较 RRC A3 配置对**真实模拟通信栈**应用包的影响，也提供了可观的默认配置改善。经过原网格、跨几何外推、A3 专用 LoRA 与最终新几何检验，**依然没有 Jev 类 Decider 超过强传统配置方法的证据**：朴素 Decider 明显落后，LoRA 只退化为固定 `(0,0)`，几何规则在未见过的场景中仍优于模型。前述 DRX LoRA 针对不同配置语义，不能移作 A3 已适配模型；本次 A3 专用训练已经单独实施，结论也为负。温度缩放不改变 Choice 最大概率选择；不能把更低交叉熵或更快推理说成业务增益。

本阶段仅有 1 UE、2 eNB、平滑规则轨迹和 ns-3 默认无线信道；不同随机运行号并不等于五个独立现场链路，边界往返场景的一些指标在五次运行中完全相同。几何规则还假设业务前知道往返周期和路径幅度，这在真实网络中须用历史测量估计，预测错误的损失未验证。未计入真实频谱干扰、复杂阴影/快衰落、多 UE 负载、功耗、RRC 重配置下发和生效时间，也没有实际 UE 抓包。进一步验证应加入可复核的阴影/衰落、不同小区密度及多 UE 竞争，并以新几何/业务留出集和有不确定性的预估输入重新比较；只有模型超过校准固定与可解释规则且置信区间排除零，才能称其有增益。最后按[真实 NR DRX 验证计划](next_validation.md)在具备 Linux gNB、UE、射频及外部电流测量时验证原始 DRX 主张，不能拿 LTE A3 结果替代 NR 功耗结论。
