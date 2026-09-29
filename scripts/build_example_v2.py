"""Render the fixed first industrial scenario with exact model input and all KPI fields."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rrcopt.policies import configuration_fragment, eligible, guard_choice
from rrcopt.simulation import Scenario


def main():
    example=json.loads(Path('artifacts/experiment/case_studies.json').read_text(encoding='utf-8'))[0]
    uid=example['scenario']['uid']
    decision=next(json.loads(line) for line in Path('artifacts/experiment/decisions.jsonl').read_text(encoding='utf-8').splitlines() if json.loads(line)['uid']==uid)
    timing=next(row for row in json.loads(Path('artifacts/temperature/per_scenario_timing.json').read_text(encoding='utf-8'))['rows'] if row['uid']==uid)
    temperature=json.loads(Path('artifacts/temperature/analysis.json').read_text(encoding='utf-8'))
    gated=next(row for row in temperature['test_gated_records'] if row['uid']==uid)['choice']
    outcome=json.loads(Path('artifacts/experiment/evaluation_metrics.json').read_text(encoding='utf-8'))[uid]
    example['choices']['decider_temperature_only']=example['choices']['decider_raw']
    example['choices']['decider_temperature_gate']=gated
    example['metrics']['decider_temperature_only']=outcome[example['choices']['decider_raw']]
    example['metrics']['decider_temperature_gate']=outcome[gated]
    adapted=next(row for row in json.loads(Path('artifacts/adaptation/test_decisions.json').read_text(encoding='utf-8')) if row['uid']==uid)
    for method,profile in [('decider_adapter_raw',adapted['raw']),('decider_adapter_screened',adapted['screened'])]:
        example['choices'][method]=profile
        example['metrics'][method]=outcome[profile]
    qwen=next(row for row in map(json.loads,Path('artifacts/qwen/decisions.jsonl').read_text(encoding='utf-8').splitlines()) if row['uid']==uid)
    scenario=Scenario(**example['scenario'])
    if qwen['profile'] is None:
        raise ValueError('This complete-sample renderer needs a valid Qwen choice')
    qwen_guard=qwen['profile'] if qwen['profile'] in eligible(scenario) else guard_choice(scenario)
    for method,profile in [('qwen_raw',qwen['profile']),('qwen_guard',qwen_guard)]:
        example['choices'][method]=profile
        example['metrics'][method]=outcome[profile]
    raw_fragment=json.dumps(configuration_fragment(example['choices']['decider_raw']),ensure_ascii=False,indent=2)
    guard_fragment=json.dumps(configuration_fragment(example['choices']['guard_only']),ensure_ascii=False,indent=2)
    s=example['scenario']
    methods=['always_on','fixed_balanced','fixed_low_latency','service_rule',
             'calibrated_fixed','calibrated_per_service','guard_only',
             'decider_raw','decider_screened','decider_temperature_only',
             'decider_temperature_gate','decider_adapter_raw',
             'decider_adapter_screened','qwen_raw','qwen_guard','hindsight_oracle']
    zh={'always_on':'DRX 关闭','fixed_balanced':'固定均衡','fixed_low_latency':'固定低时延',
        'service_rule':'传统按业务规则','calibrated_fixed':'校准集单一固定','calibrated_per_service':'校准集按业务固定',
        'guard_only':'确定性自适应规则','decider_raw':'Decider 原始输出',
        'decider_screened':'Decider + 风险筛选',
        'decider_temperature_only':'Decider 调温度 1.5',
        'decider_temperature_gate':'Decider 温度+置信度回退',
        'decider_adapter_raw':'Decider 领域 LoRA 原始',
        'decider_adapter_screened':'Decider 领域 LoRA+筛选',
        'qwen_raw':'Qwen Base 原始生成',
        'qwen_guard':'Qwen Base+单选工程回退',
        'hindsight_oracle':'事后最优（不可部署）'}
    lines=[f'''# 一条工业周期控制场景的完整输入和输出

固定选取最终测试集第一条：`{uid}`。这条数据是**合成业务场景**，公开 16 对 RRC 报文只提供了已有 MAC 参数；没有从那些报文推导以下业务负载。90 个测试场景的总体结果见[主报告](report.md)。

## 推理和仿真时间轴

每条场景先调用 Decider 一次；这条请求的本机墙钟耗时为 **{decision['inference_ms']:.3f} ms**，不加入分组时延。然后生成从 0 到 **1000 ms** 的到达时间窗，本例共有 **{example['metrics']['always_on']['packets']} 个包**。相同包到达轨迹对 9 个候选配置各模拟一次；本机 CPU 重复 3 次计时的中位数为 **{timing['simulation_wall_ms_median']:.3f} ms**（含生成到达轨迹和 9 次仿真）。下表各方法复用相应配置的结果，不是每个方法重新生成流量或再调用模型。仿真也会将 1000 ms 末尾的队列继续排空。

## Decider 真正看见的输入

`state` 完整原文：

```text
{decision['state']}
```

`question` 完整原文：

```text
{decision['question']}
```

提交给 Decider 的 `options` 顺序为：`{', '.join(decision['options'])}`。`off` 是 DRX release，保持接收可用；其余 `周期/开启时长` 均以毫秒解释。该顺序由固定随机数独立打乱，避免恒定选项位置。这里只查询一个 Choice 类型问题，返回每个候选的概率和最高概率选项，**不是**生成完整 RRC 文本。

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

输入中的数值被四舍五入到 4 位小数，仿真保留场景原始双精度值。`uid` 与随机种子 `{s['seed']}` **没有发送给模型**；其作用只是固定这条仿真轨迹。原始 RRC 内容中的身份和 NAS 载荷也未发送。

## Decider 返回的逐候选概率

| 候选配置 | 概率 | 配置接收占空比 |
|---|---:|---:|''']
    p=decision['result']['probs']
    for name in decision['options']:
        cycle,on=map(int,name.split('/')) if name!='off' else (0,0)
        duty=on/cycle if cycle else 1
        lines[-1]+=f'\n| `{name}` | {p[name]:.4f} | {100*duty:.1f}% |'
    lines.append(f'''\n最高概率是 **`{decision['result']['choice']}`，{decision['result']['confidence']:.4f}**。这是模型对选项的相对概率，不是该配置满足 5 ms 期限的概率。固定规则的风险筛选在本例只允许 `off`，因此 `decider_screened` 与 `guard_only` 都选 `off`。

## 每种方法的配置输出

| 方法 | 配置 | 本例 DRX 字段 | 策略定义 |
|---|---|---|---|''')
    for method in methods:
        name=example['choices'][method]
        setup=configuration_fragment(name)['drx-Config']
        config='`release`' if name=='off' else f"`onDurationTimer=psf{setup['setup']['onDurationTimer'][3:]}`、`longDRX-CycleStartOffset=sf{setup['setup']['longDRX-CycleStartOffset'].keys().__iter__().__next__()[2:]}:0`"
        explanation={'always_on':'始终保持接收可用的时延下界',
                     'fixed_balanced':'不看场景，固定 40/4',
                     'fixed_low_latency':'不看场景，固定 10/8',
                     'service_rule':'工业场景固定 10/8；其他业务有各自预设',
                     'calibrated_fixed':'在独立校准集上选单一配置',
                     'calibrated_per_service':'校准集按业务类别选固定配置',
                     'guard_only':'只看描述符，按容量和最坏睡眠启发式筛选后选最低占空比',
                     'decider_raw':'模型最大概率原始选择',
                     'decider_screened':'模型概率在筛选后候选中取最大',
                     'decider_temperature_only':'校准集选择温度 1.5；正温度不改变最大概率选择',
                     'decider_temperature_gate':'温度 1.5，最大概率低于 0.35 或选项不合格时退回确定性规则',
                     'decider_adapter_raw':'300 个训练描述符、每个 3 条独立相位构造标签后的 LoRA 最大概率选择',
                     'decider_adapter_screened':'领域 LoRA 概率在同一个工程筛选后的候选中取最大',
                     'qwen_raw':'三个校准示例提示后，预训练 Base 模型贪心生成单一候选',
                     'qwen_guard':'若 Qwen 候选不通过同一工程风险筛选，退回确定性规则',
                     'hindsight_oracle':'看见本场景所有候选仿真结果后选；只能作离线上界'}[method]
        lines[-1]+=f'\n| {zh[method]} | `{name}` | {config} | {explanation} |'
    lines.append(f'''\nDecider 原始选择对应的完整**规划片段**：

```json
{raw_fragment}
```

确定性规则在本例选择的片段：

```json
{guard_fragment}
```

`drx-Config.setup` 表示启用连接态 DRX；`release` 表示关闭。`onDurationTimer=psf4` 表示每次长周期起始的 4 个子帧处于接收活动期；`longDRX-CycleStartOffset=sf10:0` 表示 10 子帧长周期、起始偏移为 0。`drx-InactivityTimer=psf1` 约束调度后延续的活动期，`drx-RetransmissionTimer=psf1` 约束等待重传的活动期；这两个计时器在规划片段中固定，却**没有进入本次队列模型**。`psf`/`sf` 在本例 LTE FDD 假设下按 1 ms 子帧理解。片段尚未 ASN.1 编码或在基站发出；原有三项 MAC 值保持不变。

## 每种方法的分组时延和期限效果

| 方法 | 配置 | 均值 ms | P95 ms | P99 ms | 最大值 ms | 超时包 | 总包数 |
|---|---|---:|---:|---:|---:|---:|---:|''')
    for method in methods:
        m=example['metrics'][method]
        lines[-1]+=f"\n| {zh[method]} | `{example['choices'][method]}` | {m['mean_ms']:.3f} | {m['p95_ms']:.3f} | {m['p99_ms']:.3f} | {m['max_ms']:.3f} | {int(round(m['miss_rate']*m['packets']))}/{m['packets']} ({100*m['miss_rate']:.1f}%) | {m['packets']} |"
    lines.append('''\n`mean/P95/P99/max` 均统计所有 500 个包的“接收窗口等待 + FIFO 服务 + 固定时延”。超过 5 ms 的包算超时，恰好等于 5 ms 不算。当前约束容许至多 1% 超时包。各百分比由相同的 500 包轨迹计算。

## 接收窗口和队列容量指标

| 方法 | 接收占空比 | 饱和服务容量 (包/ms) | 负载/容量比 | 超过容量？ | 最后完成时刻 ms | 结束后排空 ms |
|---|---:|---:|---:|---|---:|---:|''')
    for method in methods:
        m=example['metrics'][method]
        lines[-1]+=f"\n| {zh[method]} | {100*m['rx_duty']:.1f}% | {m['capacity_packets_per_ms']:.3f} | {m['utilization']:.3f} | {'是' if m['overloaded'] else '否'} | {m['last_completion_ms']:.3f} | {m['drain_ms']:.3f} |"
    lines.append('''\n`rx_duty` 是开启时长除以周期的配置代理，不是实测能耗。容量按“每个窗口能完整放下多少包”计算；负载/容量比是 1 秒内的平均到达率除以该容量。即使比值小于 1，周期性休眠仍可造成 5 ms 超时。最后完成时刻是队列完成最后一个包的时间，不含附加的固定网络时延；排空表示它超出 1000 ms 输入窗的部分。

本例 Decider 原始配置 `10/4` 将接收占空比降到 40%，但 **241/500 包**错过 5 ms 期限；规则与筛选选择 `off`，所有包满足期限，占空比为 100%。这条例子展示了约束和占空比的取舍，不能推断真实终端的电池消耗或 NR 性能。
''')
    lines.append(f'''\n领域适配后的 Decider 使用完全相同的 `state`、`question` 和选项顺序，在本例推理耗时 **{adapted['inference_ms']:.3f} ms**；最高概率配置为 `{adapted['raw']}`（概率 {adapted['probs'][adapted['raw']]:.4f}），同一风险筛选后为 `{adapted['screened']}`。适配模型的其余候选概率及可复核原始请求见[逐请求结果](../artifacts/adaptation/test_decisions.json)。适配损失降低并不能自动消除本例的 5 ms 超期，以上两张表保留其原始输出和筛选后的结果。''')
    lines.append(f'''\n## Qwen Base 在同一案例中的完整提示词

它收到与 Decider 相同的目标场景描述，另外还收到三个**仅来自校准集**的示例答案；它看不到本例的仿真结果。以下是实际送入 tokenizer 的全部文本：

```text
{qwen['prompt']}
```

Qwen 以贪心方式生成的原文（保留空格和换行）：

```text
{qwen['raw_text']}```

去掉首尾空白后解析为 `{qwen['profile']}`，本例推理耗时 **{qwen['inference_ms']:.3f} ms**、生成 **{qwen['new_tokens']}** 个 token。该配置字段和所有包级指标已列在上方两张表；同一单选工程回退会将它改成 `{qwen_guard}`。更长的少样例提示词与自回归生成也是实测时延的一部分，故与 Decider 的时延差仅针对这两套具体方法。''')
    Path('docs/example_v2.md').write_text('\n\n'.join(lines),encoding='utf-8')
    print('EXAMPLE_V2_OK',len(lines))


if __name__=='__main__':main()
