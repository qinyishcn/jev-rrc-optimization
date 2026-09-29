# Qwen3.5-2B-Base 自回归对照

本对照使用 [Qwen 官方预训练权重](https://huggingface.co/Qwen/Qwen3.5-2B-Base)，固定 revision `b1485b2fa6dfa1287294f269f5fb618e03d52d7c`，权重 SHA256 `928acbf11878c32185bbd863514d191769285065ab9ea14fbfe431303f5fdf2d`。官方模型卡注明它是 **pre-trained only**，主要用于微调和上下文学习实验。这里测的是原始 Base 模型在少量示例提示下直接选择 DRX 配置的能力，不代表指令微调模型的能力。

它与 Decider 使用相同的九个配置名、`context(s, current_mac)` 中的业务描述与公开 RRC MAC 状态，以及同一批 90 个 `seed=26092902` 场景。提示词包含三个固定校准场景（`seed=26092801`）及其事后最优标签，不含任何测试场景的到达轨迹、仿真结果或最优标签。候选顺序按与 Decider 相同的 `Random(8171+idx)` 打乱。模型用 `do_sample=False` 自回归生成，最多 16 个新 token，到换行停止；没有候选 token 的 logit 限制，也没有接入 Decider 的筛选器。

只有生成文本在去除前后空白后恰好等于九个配置名之一，才形成可用配置。多选、解释文字、未列出的配置或空输出均记作 **无效、无配置**，不会暗中回退到规则配置。有效输出才按相同仿真器计算接收占空比、时延和约束违反。有效子集的平均值不能与覆盖全部 90 场景的方法直接比较；必须同时报告无效率。

在项目虚拟环境中执行：

```powershell
.venv\Scripts\python.exe scripts\run_qwen_baseline.py download
.venv\Scripts\python.exe scripts\run_qwen_baseline.py run
```

下载使用固定 Hugging Face commit 和断点续传字节范围，完整核对权重 LFS SHA256。推理在 CUDA 上运行并在计时边界同步 GPU；冷启动和预热不计入逐场景耗时。每个场景立即写入 `artifacts/qwen/decisions.jsonl`，包含原始输出、解析配置、提示词哈希关联、token 数和耗时；中断后核对请求与模型身份再继续。`status.json` 保存完成状态和证据文件 SHA256。

实际下载完成并校验 4,548,221,488 字节权重；90/90 条测试场景均真实生成并输出单一合法候选，**无效输出 0/90**。逐场景原始生成文本与耗时在[`decisions.jsonl`](../artifacts/qwen/decisions.jsonl)，每个选择对应的完整仿真指标在[`rows.json`](../artifacts/qwen/rows.json)，完成状态和文件 SHA256 在[`status.json`](../artifacts/qwen/status.json)。

| 同一批 90 场景的方法 | 推理中位数 / P95 | 超标场景 | 平均超时包比例 | 接收占空比代理 | 场景 P99 均值 |
|---|---:|---:|---:|---:|---:|
| Qwen Base 原始生成 | 1188.50 / 1238.51 ms | 48/90 | 26.84% | 33.67% | 90.727 ms |
| Decider 2B 原始 Choice | 186.24 / 216.83 ms | 36/90 | 19.20% | 46.56% | 14.363 ms |
| Qwen 原始候选 + 同一单选工程回退 | 1188.50 / 1238.51 ms | 0/90 | 0% | 58.89% | 7.872 ms |
| Decider 原始候选 + 同一单选工程回退 | 186.24 / 216.83 ms | 0/90 | 0% | 66.44% | 7.008 ms |
| 无模型工程规则 | 0 / 0 ms | 0/90 | 0% | 54.67% | 7.773 ms |

单选工程回退仅在候选不通过相同的描述符风险筛选时使用 `guard_only` 选项，不重新向模型查询；它**不同于**第一版“Decider 在全部合格候选中按概率重选”的筛选版。该对称对照使 Qwen 与 Decider 的输出经过同一后处理。Qwen 原始选择比 Decider 多 **12/90** 个超标场景，成对 bootstrap 的 95% 场景区间为 **2.22–24.44 个百分点**；但 Qwen 选择了更低的占空比，超标增多与占空比降低形成取舍。经同一单选回退后两者零超标，**Qwen 占空比低于 Decider 7.56 个百分点**，而无模型规则仍更低。全部逐条同场景比较见[`paired_comparison.json`](../artifacts/qwen/paired_comparison.json)。

固定工业案例 `26092902-industrial_control-0000` 的 Qwen 实际生成文本为 ` 40/4\n`，解析配置 `40/4`（规划片段含 `onDurationTimer=psf4`、`longDRX-CycleStartOffset=sf40:0`），推理 **1217.759 ms**；500 包中 **450 包超出 5 ms**，均值 **20.674 ms**、P95 **37.714 ms**、P99 **38.076 ms**、最大值 **38.177 ms**，占空比代理 **10%**。逐项输入和与 Decider/规则的共同轨迹结果见[完整样例](example_v2.md)。

这里比较的是**具体提示词、权重和解码方式组合**。Qwen 官方将 Base 定位为预训练权重，非指令模型；Decider 从相同底座经过大量决策任务训练。Qwen 用了三个校准示例、较长提示词及自回归生成，Decider 用 Choice 选项打分。Decider 在这套实现里推理约 **6.38 倍更快**且原始超标更少，不能据此声称其模型架构在同训练量、同提示长度或其他 RRC 任务上必然优于传统 LLM。两种原始模型均不足以满足这里的时延约束，强工程规则仍不可缺。

这些数值来自简化 LTE FDD 周期接收窗口和 FIFO 队列，不是无线链路的实测时延、功耗或可靠性。本轮虽无格式无效输出，仍有 48 个场景未满足期限，不能以格式正确代替配置有效。
