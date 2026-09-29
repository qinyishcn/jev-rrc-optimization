# 一条工业周期控制场景的完整输入和输出

固定选取最终测试集第一条：`26092902-industrial_control-0000`。这条数据是**合成业务场景**，公开 16 对 RRC 报文只提供了已有 MAC 参数；没有从那些报文推导以下业务负载。90 个测试场景的总体结果见[主报告](report.md)。

## 推理和仿真时间轴

每条场景先调用 Decider 一次；这条请求的本机墙钟耗时为 **215.929 ms**，不加入分组时延。然后生成从 0 到 **1000 ms** 的到达时间窗，本例共有 **500 个包**。相同包到达轨迹对 9 个候选配置各模拟一次；本机 CPU 重复 3 次计时的中位数为 **3.388 ms**（含生成到达轨迹和 9 次仿真）。下表各方法复用相应配置的结果，不是每个方法重新生成流量或再调用模型。仿真也会将 1000 ms 末尾的队列继续排空。

## Decider 真正看见的输入

`state` 完整原文：

```text
LTE FDD simplified periodic receive windows. Packets arriving during sleep wait for the next ON window. FIFO; each whole packet must finish within an ON window. The fixed network delay is added to queueing and service delay. Burst phase is unknown. Minimize ON fraction subject to the deadline. {"service":"industrial_control","packet_deadline_ms":5,"burst_interval_ms":4.0,"burst_jitter_plus_minus_ms":0.4467,"packets_per_burst":2,"service_time_per_packet_ms":0.1014,"fixed_network_delay_ms":3.4031,"existing_MAC_config_from_public_RRC_trace":{"periodicBSR-Timer":"sf20","retxBSR-Timer":"sf320","timeAlignmentTimerDedicated":"infinity"}}
```

`question` 完整原文：

```text
Choose the connected-mode DRX profile with the lowest receiver ON fraction that keeps packet delay within the stated deadline for at least 99% of packets. Consider base delay, sleep wait, burst queueing and available service capacity. off means always awake. Other choices are cycle/on-duration in milliseconds. Use off when the deadline cannot safely tolerate sleep. Which profile?
```

提交给 Decider 的 `options` 顺序为：`10/8, 10/2, 40/4, 20/4, 32/8, off, 80/4, 10/4, 20/8`。`off` 是 DRX release，保持接收可用；其余 `周期/开启时长` 均以毫秒解释。该顺序由固定随机数独立打乱，避免恒定选项位置。这里只查询一个 Choice 类型问题，返回每个候选的概率和最高概率选项，**不是**生成完整 RRC 文本。

| 输入字段 | 本例数值 | 含义、来源及边界 |
|---|---:|---|
| `service` | `industrial_control` | 人工设定的紧时延业务类别 |
| `packet_deadline_ms` | 5 ms | 从包到达到完成服务及附加固定延迟的期限 |
| `burst_interval_ms` | 4.0 ms | 周期性突发中心之间的时间 |
| `burst_jitter_plus_minus_ms` | 0.4467 ms | 每次突发时间的均匀随机扰动半宽；模型只见边界，未见随机实现 |
| `packets_per_burst` | 2 | 每次突发同时到达的包数 |
| `service_time_per_packet_ms` | 0.1014 ms | 简化单服务端处理每个包的时间 |
| `fixed_network_delay_ms` | 3.4031 ms | 附加固定时延；不占服务端队列容量 |
| `existing_MAC_config_from_public_RRC_trace` | `periodicBSR-Timer=sf20`, `retxBSR-Timer=sf320`, `timeAlignmentTimerDedicated=infinity` | 公开 LTE 文本中实际出现的既有参数；本实验不调这些参数 |

输入中的数值被四舍五入到 4 位小数，仿真保留场景原始双精度值。`uid` 与随机种子 `4820360743937624578` **没有发送给模型**；其作用只是固定这条仿真轨迹。原始 RRC 内容中的身份和 NAS 载荷也未发送。

## Decider 返回的逐候选概率

| 候选配置 | 概率 | 配置接收占空比 |
|---|---:|---:|
| `10/8` | 0.2040 | 80.0% |
| `10/2` | 0.0819 | 20.0% |
| `40/4` | 0.0479 | 10.0% |
| `20/4` | 0.1015 | 20.0% |
| `32/8` | 0.0311 | 25.0% |
| `off` | 0.0251 | 100.0% |
| `80/4` | 0.0265 | 5.0% |
| `10/4` | 0.2668 | 40.0% |
| `20/8` | 0.2152 | 40.0% |


最高概率是 **`10/4`，0.2668**。这是模型对选项的相对概率，不是该配置满足 5 ms 期限的概率。固定规则的风险筛选在本例只允许 `off`，因此 `decider_screened` 与 `guard_only` 都选 `off`。

## 每种方法的配置输出

| 方法 | 配置 | 本例 DRX 字段 | 策略定义 |
|---|---|---|---|
| DRX 关闭 | `off` | `release` | 始终保持接收可用的时延下界 |
| 固定均衡 | `40/4` | `onDurationTimer=psf4`、`longDRX-CycleStartOffset=sf40:0` | 不看场景，固定 40/4 |
| 固定低时延 | `10/8` | `onDurationTimer=psf8`、`longDRX-CycleStartOffset=sf10:0` | 不看场景，固定 10/8 |
| 传统按业务规则 | `10/8` | `onDurationTimer=psf8`、`longDRX-CycleStartOffset=sf10:0` | 工业场景固定 10/8；其他业务有各自预设 |
| 校准集单一固定 | `off` | `release` | 在独立校准集上选单一配置 |
| 校准集按业务固定 | `off` | `release` | 校准集按业务类别选固定配置 |
| 确定性自适应规则 | `off` | `release` | 只看描述符，按容量和最坏睡眠启发式筛选后选最低占空比 |
| Decider 原始输出 | `10/4` | `onDurationTimer=psf4`、`longDRX-CycleStartOffset=sf10:0` | 模型最大概率原始选择 |
| Decider + 风险筛选 | `off` | `release` | 模型概率在筛选后候选中取最大 |
| Decider 调温度 1.5 | `10/4` | `onDurationTimer=psf4`、`longDRX-CycleStartOffset=sf10:0` | 校准集选择温度 1.5；正温度不改变最大概率选择 |
| Decider 温度+置信度回退 | `off` | `release` | 温度 1.5，最大概率低于 0.35 或选项不合格时退回确定性规则 |
| Decider 领域 LoRA 原始 | `10/8` | `onDurationTimer=psf8`、`longDRX-CycleStartOffset=sf10:0` | 300 个训练描述符、每个 3 条独立相位构造标签后的 LoRA 最大概率选择 |
| Decider 领域 LoRA+筛选 | `off` | `release` | 领域 LoRA 概率在同一个工程筛选后的候选中取最大 |
| Qwen Base 原始生成 | `40/4` | `onDurationTimer=psf4`、`longDRX-CycleStartOffset=sf40:0` | 三个校准示例提示后，预训练 Base 模型贪心生成单一候选 |
| Qwen Base+单选工程回退 | `off` | `release` | 若 Qwen 候选不通过同一工程风险筛选，退回确定性规则 |
| 事后最优（不可部署） | `off` | `release` | 看见本场景所有候选仿真结果后选；只能作离线上界 |


Decider 原始选择对应的完整**规划片段**：

```json
{
  "drx-Config": {
    "setup": {
      "onDurationTimer": "psf4",
      "drx-InactivityTimer": "psf1",
      "drx-RetransmissionTimer": "psf1",
      "longDRX-CycleStartOffset": {
        "sf10": 0
      }
    }
  }
}
```

确定性规则在本例选择的片段：

```json
{
  "drx-Config": {
    "release": null
  }
}
```

`drx-Config.setup` 表示启用连接态 DRX；`release` 表示关闭。`onDurationTimer=psf4` 表示每次长周期起始的 4 个子帧处于接收活动期；`longDRX-CycleStartOffset=sf10:0` 表示 10 子帧长周期、起始偏移为 0。`drx-InactivityTimer=psf1` 约束调度后延续的活动期，`drx-RetransmissionTimer=psf1` 约束等待重传的活动期；这两个计时器在规划片段中固定，却**没有进入本次队列模型**。`psf`/`sf` 在本例 LTE FDD 假设下按 1 ms 子帧理解。片段尚未 ASN.1 编码或在基站发出；原有三项 MAC 值保持不变。

## 每种方法的分组时延和期限效果

| 方法 | 配置 | 均值 ms | P95 ms | P99 ms | 最大值 ms | 超时包 | 总包数 |
|---|---|---:|---:|---:|---:|---:|---:|
| DRX 关闭 | `off` | 3.555 | 3.606 | 3.606 | 3.606 | 0/500 (0.0%) | 500 |
| 固定均衡 | `40/4` | 20.674 | 37.714 | 38.076 | 38.177 | 450/500 (90.0%) | 500 |
| 固定低时延 | `10/8` | 3.773 | 5.433 | 5.610 | 5.668 | 46/500 (9.2%) | 500 |
| 传统按业务规则 | `10/8` | 3.773 | 5.433 | 5.610 | 5.668 | 46/500 (9.2%) | 500 |
| 校准集单一固定 | `off` | 3.555 | 3.606 | 3.606 | 3.606 | 0/500 (0.0%) | 500 |
| 校准集按业务固定 | `off` | 3.555 | 3.606 | 3.606 | 3.606 | 0/500 (0.0%) | 500 |
| 确定性自适应规则 | `off` | 3.555 | 3.606 | 3.606 | 3.606 | 0/500 (0.0%) | 500 |
| Decider 原始输出 | `10/4` | 5.403 | 9.458 | 9.671 | 9.707 | 241/500 (48.2%) | 500 |
| Decider + 风险筛选 | `off` | 3.555 | 3.606 | 3.606 | 3.606 | 0/500 (0.0%) | 500 |
| Decider 调温度 1.5 | `10/4` | 5.403 | 9.458 | 9.671 | 9.707 | 241/500 (48.2%) | 500 |
| Decider 温度+置信度回退 | `off` | 3.555 | 3.606 | 3.606 | 3.606 | 0/500 (0.0%) | 500 |
| Decider 领域 LoRA 原始 | `10/8` | 3.773 | 5.433 | 5.610 | 5.668 | 46/500 (9.2%) | 500 |
| Decider 领域 LoRA+筛选 | `off` | 3.555 | 3.606 | 3.606 | 3.606 | 0/500 (0.0%) | 500 |
| Qwen Base 原始生成 | `40/4` | 20.674 | 37.714 | 38.076 | 38.177 | 450/500 (90.0%) | 500 |
| Qwen Base+单选工程回退 | `off` | 3.555 | 3.606 | 3.606 | 3.606 | 0/500 (0.0%) | 500 |
| 事后最优（不可部署） | `off` | 3.555 | 3.606 | 3.606 | 3.606 | 0/500 (0.0%) | 500 |


`mean/P95/P99/max` 均统计所有 500 个包的“接收窗口等待 + FIFO 服务 + 固定时延”。超过 5 ms 的包算超时，恰好等于 5 ms 不算。当前约束容许至多 1% 超时包。各百分比由相同的 500 包轨迹计算。

## 接收窗口和队列容量指标

| 方法 | 接收占空比 | 饱和服务容量 (包/ms) | 负载/容量比 | 超过容量？ | 最后完成时刻 ms | 结束后排空 ms |
|---|---:|---:|---:|---|---:|---:|
| DRX 关闭 | 100.0% | 9.866 | 0.051 | 否 | 998.189 | 0.000 |
| 固定均衡 | 10.0% | 0.975 | 0.513 | 否 | 1001.824 | 1.824 |
| 固定低时延 | 80.0% | 7.800 | 0.064 | 否 | 1000.203 | 0.203 |
| 传统按业务规则 | 80.0% | 7.800 | 0.064 | 否 | 1000.203 | 0.203 |
| 校准集单一固定 | 100.0% | 9.866 | 0.051 | 否 | 998.189 | 0.000 |
| 校准集按业务固定 | 100.0% | 9.866 | 0.051 | 否 | 998.189 | 0.000 |
| 确定性自适应规则 | 100.0% | 9.866 | 0.051 | 否 | 998.189 | 0.000 |
| Decider 原始输出 | 40.0% | 3.900 | 0.128 | 否 | 1000.203 | 0.203 |
| Decider + 风险筛选 | 100.0% | 9.866 | 0.051 | 否 | 998.189 | 0.000 |
| Decider 调温度 1.5 | 40.0% | 3.900 | 0.128 | 否 | 1000.203 | 0.203 |
| Decider 温度+置信度回退 | 100.0% | 9.866 | 0.051 | 否 | 998.189 | 0.000 |
| Decider 领域 LoRA 原始 | 80.0% | 7.800 | 0.064 | 否 | 1000.203 | 0.203 |
| Decider 领域 LoRA+筛选 | 100.0% | 9.866 | 0.051 | 否 | 998.189 | 0.000 |
| Qwen Base 原始生成 | 10.0% | 0.975 | 0.513 | 否 | 1001.824 | 1.824 |
| Qwen Base+单选工程回退 | 100.0% | 9.866 | 0.051 | 否 | 998.189 | 0.000 |
| 事后最优（不可部署） | 100.0% | 9.866 | 0.051 | 否 | 998.189 | 0.000 |


`rx_duty` 是开启时长除以周期的配置代理，不是实测能耗。容量按“每个窗口能完整放下多少包”计算；负载/容量比是 1 秒内的平均到达率除以该容量。即使比值小于 1，周期性休眠仍可造成 5 ms 超时。最后完成时刻是队列完成最后一个包的时间，不含附加的固定网络时延；排空表示它超出 1000 ms 输入窗的部分。

本例 Decider 原始配置 `10/4` 将接收占空比降到 40%，但 **241/500 包**错过 5 ms 期限；规则与筛选选择 `off`，所有包满足期限，占空比为 100%。这条例子展示了约束和占空比的取舍，不能推断真实终端的电池消耗或 NR 性能。



领域适配后的 Decider 使用完全相同的 `state`、`question` 和选项顺序，在本例推理耗时 **246.854 ms**；最高概率配置为 `10/8`（概率 0.5797），同一风险筛选后为 `off`。适配模型的其余候选概率及可复核原始请求见[逐请求结果](../artifacts/adaptation/test_decisions.json)。适配损失降低并不能自动消除本例的 5 ms 超期，以上两张表保留其原始输出和筛选后的结果。


## Qwen Base 在同一案例中的完整提示词

它收到与 Decider 相同的目标场景描述，另外还收到三个**仅来自校准集**的示例答案；它看不到本例的仿真结果。以下是实际送入 tokenizer 的全部文本：

```text
LTE connected-mode DRX profile selection.
Choose the connected-mode DRX profile with the lowest receiver ON fraction that keeps packet delay within the stated deadline for at least 99% of packets. Consider base delay, sleep wait, burst queueing and available service capacity. off means always awake. Other choices are cycle/on-duration in milliseconds. Use off when the deadline cannot safely tolerate sleep. Which profile?
Valid profiles: 10/8, 10/2, 40/4, 20/4, 32/8, off, 80/4, 10/4, 20/8.
Reply with exactly one profile name, with no explanation.
State: LTE FDD simplified periodic receive windows. Packets arriving during sleep wait for the next ON window. FIFO; each whole packet must finish within an ON window. The fixed network delay is added to queueing and service delay. Burst phase is unknown. Minimize ON fraction subject to the deadline. {"service":"industrial_control","packet_deadline_ms":5,"burst_interval_ms":1.0,"burst_jitter_plus_minus_ms":0.0791,"packets_per_burst":3,"service_time_per_packet_ms":0.1752,"fixed_network_delay_ms":3.0668,"existing_MAC_config_from_public_RRC_trace":{"periodicBSR-Timer":"sf20","retxBSR-Timer":"sf320","timeAlignmentTimerDedicated":"infinity"}}
Profile: off
State: LTE FDD simplified periodic receive windows. Packets arriving during sleep wait for the next ON window. FIFO; each whole packet must finish within an ON window. The fixed network delay is added to queueing and service delay. Burst phase is unknown. Minimize ON fraction subject to the deadline. {"service":"xr","packet_deadline_ms":10,"burst_interval_ms":16.6667,"burst_jitter_plus_minus_ms":2.7134,"packets_per_burst":4,"service_time_per_packet_ms":0.1896,"fixed_network_delay_ms":4.1878,"existing_MAC_config_from_public_RRC_trace":{"periodicBSR-Timer":"sf20","retxBSR-Timer":"sf320","timeAlignmentTimerDedicated":"infinity"}}
Profile: 10/8
State: LTE FDD simplified periodic receive windows. Packets arriving during sleep wait for the next ON window. FIFO; each whole packet must finish within an ON window. The fixed network delay is added to queueing and service delay. Burst phase is unknown. Minimize ON fraction subject to the deadline. {"service":"gaming","packet_deadline_ms":20,"burst_interval_ms":10.0,"burst_jitter_plus_minus_ms":0.427,"packets_per_burst":4,"service_time_per_packet_ms":0.131,"fixed_network_delay_ms":3.2024,"existing_MAC_config_from_public_RRC_trace":{"periodicBSR-Timer":"sf20","retxBSR-Timer":"sf320","timeAlignmentTimerDedicated":"infinity"}}
Profile: 10/2
State: LTE FDD simplified periodic receive windows. Packets arriving during sleep wait for the next ON window. FIFO; each whole packet must finish within an ON window. The fixed network delay is added to queueing and service delay. Burst phase is unknown. Minimize ON fraction subject to the deadline. {"service":"industrial_control","packet_deadline_ms":5,"burst_interval_ms":4.0,"burst_jitter_plus_minus_ms":0.4467,"packets_per_burst":2,"service_time_per_packet_ms":0.1014,"fixed_network_delay_ms":3.4031,"existing_MAC_config_from_public_RRC_trace":{"periodicBSR-Timer":"sf20","retxBSR-Timer":"sf320","timeAlignmentTimerDedicated":"infinity"}}
Profile:
```

Qwen 以贪心方式生成的原文（保留空格和换行）：

```text
 40/4
```

去掉首尾空白后解析为 `40/4`，本例推理耗时 **1217.759 ms**、生成 **6** 个 token。该配置字段和所有包级指标已列在上方两张表；同一单选工程回退会将它改成 `off`。更长的少样例提示词与自回归生成也是实测时延的一部分，故与 Decider 的时延差仅针对这两套具体方法。