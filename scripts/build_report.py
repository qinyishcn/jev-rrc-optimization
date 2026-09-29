"""Build report and scientific figures only from completed, hash-verified evidence."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from rrcopt.provenance import file_hash

ROOT = Path('artifacts/experiment')
LABELS = {'always_on':'关闭 DRX', 'fixed_balanced':'固定 40/4', 'fixed_low_latency':'固定 10/8',
          'service_rule':'按业务规则', 'calibrated_fixed':'校准集选单一配置',
          'calibrated_per_service':'校准集按业务选配置', 'guard_only':'确定性自适应规则',
          'decider_raw':'Decider 原始选择', 'decider_screened':'Decider + 候选筛选',
          'hindsight_oracle':'事后最优（不可部署）'}
SERVICES = {'all':'总体（业务等权）','industrial_control':'工业周期控制：5 ms',
            'xr':'交互式 XR：10 ms','gaming':'交互游戏：20 ms'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def table(rows):
    lines = ['| 方法 | 场景 P99 均值 (ms) | 超时包比例均值 (%) | 超标场景 | 接收占空比 (%) |',
             '|---|---:|---:|---:|---:|']
    for row in rows:
        n = row['n_scenarios']
        lines.append(f"| {LABELS[row['method']]} | {row['mean_scenario_p99_ms']:.3f} | {100*row['mean_miss_rate']:.3f} | {round(row['scenario_violation_rate']*n)}/{n} | {100*row['mean_rx_duty']:.2f} |")
    return '\n'.join(lines)


def main():
    status = read(ROOT/'status.json')
    if status.get('state')!='complete' or not status.get('model_evaluated'):
        raise RuntimeError('Completed actual-model run required')
    for name,digest in status['evidence_sha256'].items():
        if file_hash(ROOT/name)!=digest:
            raise RuntimeError(f'Evidence checksum mismatch: {name}')
    summary = read(ROOT/'summary.json')
    smoke = read('artifacts/model_smoke.json')
    protocol = read('artifacts/protocol_model_smoke.json')
    design = read(ROOT/'design.json')
    decisions = [json.loads(line) for line in (ROOT/'decisions.jsonl').read_text(encoding='utf-8').splitlines()]
    valid_ids = {r['uid'] for r in read(ROOT/'evaluation_scenarios.json')}
    decisions = [r for r in decisions if r['uid'] in valid_ids]
    durations = [r['inference_ms'] for r in decisions]
    all_rows = {r['method']:r for r in summary if r['service']=='all'}
    order = ['always_on','fixed_low_latency','service_rule','calibrated_per_service','guard_only','decider_raw','decider_screened','hindsight_oracle']
    en = ['Always ON','Fixed 10/8','Service rule','Calibrated per service','Adaptive rule','Decider raw','Decider + screen','Hindsight oracle']
    fig, axes = plt.subplots(1,3,figsize=(14,5.2),sharey=True)
    colors = ['#8996a6','#8996a6','#8996a6','#8996a6','#16917f','#dd7934','#536fc1','#b9a0cd']
    for ax,key,title,mult in zip(axes,['mean_scenario_p99_ms','mean_miss_rate','mean_rx_duty'],
                               ['Mean of scenario P99 delays (ms)','Mean deadline miss rate (%)','Configured RX duty (%)'],[1,100,100]):
        values=[all_rows[m][key]*mult for m in order]
        ax.barh(np.arange(len(order)),values,color=colors,height=.65)
        ax.set_title(title,fontsize=11)
        ax.set_yticks(np.arange(len(order)),en)
        ax.grid(axis='x',alpha=.2)
        ax.set_axisbelow(True)
        ax.set_xlim(0,max(values)*1.22 if max(values)>0 else 1)
        for i,v in enumerate(values):
            ax.text(v+ax.get_xlim()[1]*.012,i,f'{v:.2f}',va='center',fontsize=9)
    axes[0].invert_yaxis()
    fig.suptitle(f'Synthetic LTE receive-window experiment | {design["n_evaluation"]} paired scenarios',fontsize=14)
    fig.text(.5,.01,'Not real-network latency or battery measurements. Equal weight per scenario. Fixed 40/4 stress baseline is in the report table.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.035,1,.95))
    Path('docs/figures').mkdir(exist_ok=True)
    fig.savefig('docs/figures/comparison.png',dpi=170)
    svg_path = Path('docs/figures/comparison.svg')
    fig.savefig(svg_path)
    svg_path.write_text('\n'.join(line.rstrip() for line in svg_path.read_text(encoding='utf-8').splitlines())+'\n', encoding='utf-8')
    plt.close(fig)
    raw, screened, guard = (all_rows[k] for k in ['decider_raw','decider_screened','guard_only'])
    n = design['n_evaluation']
    conclusion = (f"Decider 原始选择在 {round(raw['scenario_violation_rate']*n)}/{n} 个场景超出约束；"
                  f"加入筛选后为 {round(screened['scenario_violation_rate']*n)}/{n}，"
                  f"确定性自适应规则为 {round(guard['scenario_violation_rate']*n)}/{n}。"
                  f"三者平均接收占空比分别为 {100*raw['mean_rx_duty']:.2f}%、"
                  f"{100*screened['mean_rx_duty']:.2f}%、{100*guard['mean_rx_duty']:.2f}%。")
    sections = [f'''# Jev 类模型用于无线 RRC 配置：可复现原型与实验报告

本项目已运行真实 **Mapika/Decider 2B v11** 权重，将有限选项决策接入 LTE RRC 配置片段生成，并完成本机推理测试与合成分组场景对照。**没有完成真实无线网络部署，也未证明优于传统自适应算法的网络性能增益。**

{conclusion}

这些结果衡量指定模型下的配置取舍。占空比越低表示配置的接收窗口越少，不代表测得电池能耗下降；时延越低也可能只是付出了更高占空比。

## 1. 实际部署和验证

| 组件 | 实际执行结果 |
|---|---|
| Decider 代码 | 固定 commit `23579f7a7e8f10e1045be492af3c1c05a005d67c`；相关上游单元测试 158 项通过 |
| Decider 模型 | 固定 HF revision `533964dae8be954c5b5e19fa4948e48408094c1e`；3,763,692,048 字节，完整 SHA256 与 LFS 一致 |
| 模型运行环境 | {smoke['device']}；torch {smoke['packages']['torch']}，transformers {smoke['packages']['transformers']}；BF16、eager |
| 公开 RRC 数据 | 全部 16 对 LTE 文本已读取、哈希已核验；无 DRX、负载、业务包时延或配置干预标签 |
| 上游模拟器 | 运行日志解析、QA 配对与简化信道函数；37 条消息形成 16 对 QA；完整 CLI 缺 pcap，未运行 Linux/srsRAN 无线栈 |
| 集成路径 | 上游解析器 → 白名单 MAC 上下文 → Decider 类型化选择 → DRX 配置片段 → 独立合成分组评估 |

权重 SHA256：`{smoke['weights_sha256']}`。代码、配置和 tokenizer 的实际哈希见 [模型身份记录](../artifacts/experiment/model_identity.json)。单次真实推理返回候选内选项和归一化概率，测试还覆盖 Jev 风格 Choice / Noul / Score 接口。Decider 是独立复现的模型类别，不能把它的结果归于闭源 Jev。

独立协议小样本测试：{protocol['input_rows']} 行合并后只有 {protocol['unique_ul_contexts']} 种不同 UL 类型上下文，模型输出在 {protocol['matching_contexts']} 种上下文中匹配某个观察到的首条 DL 类型。省略 NAS/网络状态后存在歧义，多行还来自重复流程；这是接口 sanity check，不能视为泛化准确率或论文复现。

## 2. 数据和参考论文为何不能直接给出优化收益

公开数据保留 `periodicBSR-Timer=sf20`、`retxBSR-Timer=sf320`、`timeAlignmentTimerDedicated=infinity` 等已有 MAC 参数作为上下文；这些字段本次不调优。新增 DRX 不是从 16 条记录训练得到，也没有据其墙钟差校准包时延。

参考论文 v5 研究 LLM 的 RRC 消息仿真、协议符合性和推理延迟，主实验语料是私有数据。其语义相似度改善不能解释成业务时延收益。上游模拟器中发现随机时延占位函数，因此没有用那些数值当优化结果。详见[逐来源审计](source_audit.md)，以及[论文 v5](https://arxiv.org/pdf/2505.16821v5)。

## 3. 配置问题与实验假设

目标：每个场景中超出业务截止时间的包不超过 1%，在此约束下尽量降低配置接收占空比。候选为 `off, 10/8, 10/4, 10/2, 20/8, 20/4, 32/8, 40/4, 80/4`，数字为周期/开启时长。两个字段的枚举来自 LTE TS 36.331；本实验假设 FDD 每毫秒可监控 PDCCH。

FIFO、周期接收窗口、整包服务、场景内固定服务时间和外加基础时延。所有到达包都排空并计入统计，包括过载下的包。工业周期控制、XR、游戏的合成截止时间分别为 5/10/20 ms；这些是实验选择，不是声称应用或 NR URLLC 标准要求。每场景到达窗口 1 秒，每业务 30 个独立场景。

模型只见已知业务描述、基础时延、突发负载与 MAC 上下文，**看不到未来到达时间、随机种子、候选仿真结果或最优标签**。相同流量同时用于全部方法。90 个校准场景用于选择固定基线；90 个新场景用于最终测试。校准 seed={design['calibration_seed']}，最终测试 seed={design['evaluation_seed']}；旧 seed=26092802 的基线探索不用于下表。提示词/规则冻结证据见 [experiment_freeze.json](../artifacts/experiment_freeze.json)。未做领域微调，也未使用外部付费模型 API。

没有模拟 inactivity 引起的 Active Time 延长、短 DRX、HARQ、误码、调度请求、无线干扰、多用户共享和 RRC 重配置开销。输出包含 inactivity/retransmission 必填字段，但数值没有参与队列模型，因而配置片段只是规划产物，尚未完成 ASN.1 编码或发送。[完整仿真定义](simulation.md)

## 4. 对照结果

“超标场景”指超时包比例大于 1%；“场景 P99 均值”是每场景 P99 的等权平均，**不是所有包合并后的 P99**。

![对照结果](figures/comparison.png)
''']
    for svc,title in SERVICES.items():
        sections.append('### '+title+'\n\n'+table([r for r in summary if r['service']==svc]))
    sections.append('''## 5. 模型贡献与传统方法的比较

固定 40/4 只作省电/容量压力参照，常因容量不足造成长队列；对它很大的时延百分比改善不能证明 AI 有价值。主要比较应同时看确定性自适应规则、校准集按业务选配置，以及始终开启的时延下界。

候选筛选器根据睡眠间隔、基础时延、突发服务需求和容量余量排除风险配置；这是一条工程启发式，未证明安全上界。`guard_only` 在同一筛选集合中直接选最低占空比，所以 **`decider_screened` 的占空比不可能低于它**。若模型选择了更短时延、更高占空比，那是另一个取舍，不能宣称在原定目标下优于规则。原始模型保留为消融对照，防止把规则贡献算给模型。

下表采用成对场景差值，正值表示前者相比基线降低指标；括号为 2,000 次场景 bootstrap 的逐项 95% 区间，总体按业务分层。它们是探索性区间，没有多重比较校正。零超时或退化区间不证明实际网络可靠性。

| 方法 vs 基线 | P99 均值降低 (ms) | 超时包比例降低 (百分点) | 占空比降低 (百分点) |
|---|---:|---:|---:|''')
    ci = read(ROOT/'paired_intervals.json')
    for method,base in [('decider_raw','guard_only'),('decider_screened','guard_only'),('decider_raw','calibrated_per_service'),('decider_screened','calibrated_per_service')]:
        vals=[]
        for metric,mul in [('p99_ms',1),('miss_rate',100),('rx_duty',100)]:
            row=next(r for r in ci if r['service']=='all' and r['method']==method and r['baseline']==base and r['metric']==metric)
            lo,hi=row['ci95']
            vals.append(f"{mul*row['baseline_minus_method']:.3f} [{mul*lo:.3f}, {mul*hi:.3f}]")
        sections[-1] += '\n'+f"| {LABELS[method]} vs {LABELS[base]} | "+' | '.join(vals)+' |'
    sections.append(f'''\n## 6. 推理耗时与部署位置

简单决策 smoke 的暖态中位数 **{smoke['warm_median_ms']:.1f} ms**，P95 **{smoke['warm_p95_ms']:.1f} ms**（10 次）。真实实验请求的中位数 **{np.median(durations):.1f} ms**，P95 **{np.percentile(durations,95):.1f} ms**（{len(durations)} 次）。CUDA 同步后按串行端到端调用计时，包含 tokenization/前向/结果组装；不含首次加载。未启用 CUDA graph、FLA/Triton 加速或量化，不能把这个 Windows eager 结果视作模型的速度极限。模型加载耗时 {smoke['load_s']:.1f} 秒，smoke 峰值已分配显存约 {smoke['peak_allocated_gb']:.2f} GB。

这些推理耗时相对 5/10/20 ms 的业务期限需要单独判断。当前方案在场景/业务建立前计算配置，包级评估不加推理延迟；这是提前配置假设，不能用于声称模型可逐包实时决策。未知突发、模型冷启动、RRC 信令和配置生效延迟均需另测。

## 7. 具体用例与输出

以下用例固定取每种业务的第一条测试场景，不按结果挑选。所有结果见 [case_studies.json](../artifacts/experiment/case_studies.json)。
''')
    for case in read(ROOT/'case_studies.json'):
        s=case['scenario']
        sections.append(f"### {SERVICES[s['service']]}\n\n周期 {s['period_ms']:.3f} ms，每次 {s['burst_packets']} 包，单包服务 {s['packet_service_ms']:.3f} ms，外加基础时延 {s['base_delay_ms']:.3f} ms。\n\n| 方法 | 配置 | P99 (ms) | 超时包 (%) | 占空比 (%) |\n|---|---|---:|---:|---:|")
        for m in ['decider_raw','decider_screened','guard_only','calibrated_per_service','fixed_low_latency']:
            r=case['metrics'][m]
            sections[-1] += '\n'+f"| {LABELS[m]} | {case['choices'][m]} | {r['p99_ms']:.3f} | {100*r['miss_rate']:.3f} | {100*r['rx_duty']:.2f} |"
        sections.append('\n输出规划片段：\n\n```json\n'+json.dumps(case['recommended_fragment'],indent=2,ensure_ascii=False)+'\n```')
    sections.append('''## 8. 结论、复现与尚未完成的验证

这次工作证明了开源 Jev 类模型在本机运行并接入类型化 RRC 参数选择的技术可行性，也给出了明确的负面/局限性证据。对于这里九个候选和已知数值约束，传统规则或直接枚举很有竞争力，不能预设大模型必然更优。需要扩展到模型能利用但简单规则难表达的历史、异常或多目标上下文，再以独立数据检验额外价值。

若要声称实际 NR 紧时延收益，后续必须使用可信无线栈/测试床的配置干预数据，补充完整 Active Time、信道/重传、多用户、配置生效成本，并做真实逐包测量。当前未完成这些步骤，未证明五个九可靠性，也未复现论文的私有训练集实验。

- [完整复现步骤](reproduce.md)
- [实际逐场景结果](../artifacts/experiment/rows.json)、[概率与耗时](../artifacts/experiment/decisions.jsonl)、[完成状态与哈希](../artifacts/experiment/status.json)
- [来源审计](source_audit.md)、[模型功能测试](../artifacts/model_smoke.json)、[协议小样本测试](../artifacts/protocol_model_smoke.json)
- [Decider](https://github.com/Mapika/decider)、[RRC 模拟器](https://github.com/EE-zim/nrRRC_Simulator)、[公开数据](https://huggingface.co/datasets/EEzim/RRC)
''')
    Path('docs/report.md').write_text('\n\n'.join(sections),encoding='utf-8')
    print(conclusion)
    print(f'Inference median={np.median(durations):.2f}ms p95={np.percentile(durations,95):.2f}ms')
    print('REPORT_OK')


if __name__=='__main__':
    main()
