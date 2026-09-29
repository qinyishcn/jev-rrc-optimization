# 复现说明

本项目分为公开 RRC 来源审计、真实 Decider 推理和独立合成 DRX 场景评估。网络时延数字来自声明过假设的队列模型；公开 RRC 数据只提供协议及 MAC 配置上下文。运行命令不代表测试已通过，最终应核对工件中的完成状态和哈希。

## 固定输入

| 输入 | 版本 |
|---|---|
| [Mapika/decider 源码](https://github.com/Mapika/decider/tree/23579f7a7e8f10e1045be492af3c1c05a005d67c) | `23579f7a7e8f10e1045be492af3c1c05a005d67c`，包版本 1.6.0 |
| [Decider 2B v11](https://huggingface.co/Mapika/decider-2b/tree/533964dae8be954c5b5e19fa4948e48408094c1e) | `533964dae8be954c5b5e19fa4948e48408094c1e` |
| [nrRRC_Simulator](https://github.com/EE-zim/nrRRC_Simulator/tree/228ad4bc7ebce1093e215a9285ee126eb862ee95) | `228ad4bc7ebce1093e215a9285ee126eb862ee95` |
| [EEzim/RRC](https://huggingface.co/datasets/EEzim/RRC/tree/e473ea8b9891f608afb7d9ad89c412e2dda27e18) | `e473ea8b9891f608afb7d9ad89c412e2dda27e18`，16 对 LTE 消息 |

权重 `model.safetensors`：3,763,692,048 字节，SHA256 `acaef2228b134dcdc20cad4ee79219482c927ec819aa3687b9b8a575c338817f`。下载器会校验 LFS 哈希，按 HTTP range 断点续传。分块缓存会保留另一份约 3.76 GB 数据；加上最终模型、临时拼接文件、Python/CUDA 包及 pip 缓存，应留出明显多于模型大小的空间，建议至少 15 GB 可用磁盘。

本机环境是 Windows、Python 3.12.10、RTX 3070 8 GB；`.venv` 开启 `--system-site-packages`，复用已有 `torch 2.6.0+cu124`，本地环境使用 `transformers 5.6.2`、`numpy 1.26.4`。这不是完全隔离环境的全新安装验证。下方另给出干净环境安装路径；GPU 内存是否足够仍以实际模型 smoke 为准。CPU/macOS 无 GPU 的完整实验不在这些脚本的支持路径内，脚本显式使用 CUDA。

## Windows 干净环境

在仓库根目录执行；要求已有 Git、Python 3.12 和可用的 NVIDIA 驱动。所有 Python 安装均写入项目虚拟环境，不使用全局 `pip install`。不要在已有实验目录中重建正在使用的 `.venv`。

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_sources.ps1
.venv\Scripts\python.exe -m pip install -e external/decider --no-deps
.venv\Scripts\python.exe -c "import torch; print(torch.__version__); assert torch.cuda.is_available(); print(torch.cuda.get_device_name())"
```

CUDA wheel 索引和版本组合来自 [PyTorch 官方旧版本安装页](https://pytorch.org/get-started/previous-versions/)。仅安装需要的 `torch`，本实验无需 torchvision/torchaudio。`ExecutionPolicy Bypass` 仅作用于此 PowerShell 子进程；没有修改系统执行策略。源码脚本检查既有 checkout 的提交号，不会自动覆盖不同版本。

本机复用已有 CUDA PyTorch 的方式是 `py -3.12 -m venv --system-site-packages .venv`，随后仍用 `.venv\Scripts\python.exe -m pip ...` 安装项目依赖。此方式只适合已确认基础包版本的环境；不建议将其当作跨机器的干净复现方案。

上游依赖声明含 `flash-linear-attention`。Windows 路径有意只安装 eager 推理所需的依赖子集，并通过 `--no-deps` 跳过上游全量依赖安装；所有模型脚本设置 `use_graphs=False`，不启用 CUDA graphs/FLA 加速。`pip check` 因未安装 FLA 而给出缺失依赖提示，不应被误报为完整上游依赖安装成功；同样不需要为了消除此提示安装训练、游戏、服务端等全部 extras。

## 下载、验证和执行

命令均从仓库根目录运行。UTF-8 模式用于绕过上游日志解析器在 Windows 默认 GBK 下的读取错误。

```powershell
.venv\Scripts\python.exe -X utf8 scripts/audit_rrc_sources.py
.venv\Scripts\python.exe -X utf8 scripts/protocol_bridge.py
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe -X utf8 scripts/download_model.py
.venv\Scripts\python.exe -X utf8 scripts/model_smoke.py
.venv\Scripts\python.exe -X utf8 scripts/protocol_model_smoke.py
.venv\Scripts\python.exe -X utf8 scripts/run_experiment.py
```

先确认下载器输出 `DOWNLOAD_OK` 和模型 smoke 输出 `MODEL_SMOKE_OK`。模型 smoke 检查实际权重加载、选项概率和 typed API，并保存 `artifacts/model_smoke.json`；小型协议 probe 保存 `artifacts/protocol_model_smoke.json`，只做消息类型 sanity check，不是独立泛化基准。

来源审计默认使用表中的固定数据集 revision。已下载后可运行 `scripts/audit_rrc_sources.py --offline` 重检；这会重写聚合审计时间。若只有 arXiv 下载出现 Python TLS 信任链错误，脚本记录错误并继续数据审计；如需本地论文，可用系统信任链下载后离线重跑，勿禁用 TLS 验证：

```powershell
Invoke-WebRequest -Uri 'https://arxiv.org/pdf/2505.16821v5' -OutFile 'data/rrc/2505.16821v5.pdf'
.venv\Scripts\python.exe -X utf8 scripts/audit_rrc_sources.py --offline
```

nrRRC 完整 CLI 在本机报缺少 `pcap`，该限制保留在审计中；这里没有安装其重型抓包依赖，也没有启动 Linux srsRAN/EPC/UE 无线栈。不要把成功运行协议桥接解释为完整模拟器部署。[来源边界](source_audit.md)与[队列模型](simulation.md)列出了具体范围。

## 结果和断点续跑

最终实验默认每业务 30 个场景，共 90 个评估场景；另有 90 个校准场景。校准种子为 `26092801`，最终评估种子为 **`26092902`**。`26092802` 是 pilot，仅用于开发检查，不用于最终收益结论。冻结记录在 `artifacts/experiment_freeze.json`。

完整运行写入 `artifacts/experiment/`。判断成功须同时满足：

- `status.json` 的 `state` 为 `complete`、`model_evaluated` 为 `true`，评估种子正确。
- `design.json` 中 `n_evaluation=90`，存在真实 `decisions.jsonl`、`model_identity.json`、`rows.json`、`summary.json`、`paired_intervals.json`。
- `status.json` 中证据文件及代码的 SHA256 与当前文件一致。目录存在、权重下载成功或进度日志走完都不能单独证明最终实验完成。

```powershell
.venv\Scripts\python.exe -c "import json,hashlib,pathlib; p=pathlib.Path('artifacts/experiment'); s=json.loads((p/'status.json').read_text()); assert s['state']=='complete' and s['model_evaluated'] and s['evaluation_seed']==26092902; assert json.loads((p/'design.json').read_text())['n_evaluation']==90; assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in s['evidence_sha256'].items()); assert all(hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest()==h for n,h in s['source_sha256'].items()); print('VERIFIED_COMPLETE')"
```

中断后重跑同一完整命令，脚本按请求、实际模型文件、推理代码及环境身份哈希复用 `decisions.jsonl`，并重算指标；恢复运行时的缓存推理耗时仍是首次产生该决策时的测量值。摘要采用场景等权，`mean_scenario_p99_ms` 不是所有包混合后的 p99。不同 CUDA/GPU 环境的概率与时间不保证逐位相同。

只评估 CPU 基线时，显式用不同目录：

```powershell
.venv\Scripts\python.exe -X utf8 scripts/run_experiment.py --baselines-only --output artifacts/baselines
```

`--baselines-only` 默认目录本来就是 `artifacts/baselines/`；不要把它的 `--output` 指到 `artifacts/experiment/`，否则会覆盖真实模型结果摘要。基线运行的 `model_evaluated=false`，不能用于声称已测 Decider。小规模探索同样使用新目录，例如 `--n-per-service 2 --output artifacts/smoke_experiment`；这不满足最终 90 场景验收。

## Linux CUDA 路径

以下是对应的移植步骤，未宣称已在 Linux 独立执行。使用 Python 3.12 和 NVIDIA CUDA 环境，仍固定 eager 引擎，不借机改变加速器/提示词后混用结果。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
.venv/bin/python -m pip install -r requirements.txt
mkdir -p external artifacts data models
git clone --no-checkout https://github.com/Mapika/decider.git external/decider
git -C external/decider checkout --detach 23579f7a7e8f10e1045be492af3c1c05a005d67c
git clone --no-checkout https://github.com/EE-zim/nrRRC_Simulator.git external/nrrrc
git -C external/nrrrc checkout --detach 228ad4bc7ebce1093e215a9285ee126eb862ee95
.venv/bin/python -m pip install -e external/decider --no-deps
.venv/bin/python -X utf8 scripts/audit_rrc_sources.py
.venv/bin/python -X utf8 scripts/protocol_bridge.py
.venv/bin/python -m pytest tests -q
.venv/bin/python -X utf8 scripts/download_model.py
.venv/bin/python -X utf8 scripts/model_smoke.py
.venv/bin/python -X utf8 scripts/protocol_model_smoke.py
.venv/bin/python -X utf8 scripts/run_experiment.py
```

已有 checkout 时跳过 clone，并核对 `git -C external/decider rev-parse HEAD` 与 `git -C external/nrrrc rev-parse HEAD`，不要覆盖本地修改。原始数据、外部源码、权重和缓存均留在被忽略的目录；仅公开经过脱敏的聚合工件。第三方许可见 [NOTICE](../NOTICE.md)。
