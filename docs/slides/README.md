# 业务语义辅助 RRC 配置优化

2026-10-09，中文 16:9 技术汇报，共 16 页（15 页正文、1 页指标附录）。深蓝与青色配色，保留可编辑文字、9 张表格和 3 张原生图表。图表内嵌工作簿保存展示用数据快照，讲者备注提供解释与证据链接。

- **[下载 PowerPoint](semantic_rrc_uc_20261009_release.pptx)**
- **[在线阅读 PDF](semantic_rrc_uc_20261009_release.pdf)**
- [页面总览](semantic_rrc_uc_preview.png)
- [制作源码](build_semantic_uc.mjs)
- [文件与证据校验值](manifest.json)

![16 页总览](semantic_rrc_uc_preview.png)

## 本次汇报的核心结论

在合成 AGV 调度确认集中，基础 Decider 2B 识别当前生效的“单向穿越 / 边界巡检”任务，再交给冻结的无线策略映射，超时/丢包率为 **0.0610%**。同文本 TF-IDF + 逻辑回归为 **0.2391%**，相对下降 **74.5%**。已知正确结构化意图的传统控制器为 **0.0500%**，仍然更好。

因此，当前增益支持少标签条件下的非结构化任务语义接口价值。它尚未证明 Decider 的无线数值寻优优于传统控制器。结果来自 ns-3 LTE A3 软件系统仿真，尚无真实 RF、NR 或商业 AGV 可靠性结论。相对 Qwen 单次前向的默认顺序性能差值区间触及零，同为单次前向时中位速度仅约 1.05 倍。

## 页面安排

| 页码 | 内容 |
|---|---|
| 1 | 标题与研究范围 |
| 2–3 | 应用背景、相同观测下的任务差异、A3 参数机制 |
| 4 | Decider 语义识别与校准策略的实现分工 |
| 5–6 | 仿真配置、校准/测试分离、语言确认集 |
| 7–8 | 主结果、基线、置信区间与增益来源 |
| 9–10 | 完整输入、穿越/巡检配对输出与分组指标 |
| 11 | Qwen3.5-2B-Base 的顺序与推理时延对照 |
| 12–13 | 原数值配置没有增益的原因、模型错误与适用边界 |
| 14–15 | Future work 与结论 |
| 16 | 确认集完整指标及证据入口 |

## 证据来源

本 PPT 对既有证据做讲解，没有新增模型或无线实验。所有主结果采用默认选项顺序，未将事后表现更好的反序作为主结论。

- [完整研究报告](../rrc_cause_semantic_uc.md)
- [聚合指标和成对置信区间](../../artifacts/semantic_uc/summary.json)
- [配对样例的完整输入、配置与逐包结果](../../artifacts/semantic_uc/example.json)
- [软件、模型与实验来源](../../artifacts/semantic_uc/provenance.json)
- [LTE A3 仿真代码](../../system_validation/ns3_lte_handover.cc)

讲者备注中的引用固定到证据提交 `2d82463f8fa5b988bb3f16aaed3a25ecf1d3cb7d`。页面 3 的位置曲线由既有运动规则计算，属于预设轨迹示意，不是新测量。确认集的语言改写复用 150 次测试物理结果，不能把关联表中的分组数当作独立新增实验。

## 重新制作

源码使用 `@oai/artifact-tool`，不是图片铺满页面的 PPT。需要兼容的 Node.js、该包、含 Microsoft YaHei 的字体环境，以及 Codex Presentations 技能中的验证工具。环境变量均为本机工具路径，无须凭证。

1. 将运行时 `node_modules` 链接到本目录的临时 `node_modules`，或在具备该包的 Node 环境中运行源码。
2. 设置 `PRESENTATIONS_SKILL_DIR`、`RUNTIME_NODE_MODULES`、`RUNTIME_PYTHON`。源码读取仓库内的 `summary.json` 与 `example.json`。
3. 设置新的 `PPT_FINAL_NAME`，如 `semantic_rrc_uc_rebuilt.pptx`，再执行 `node docs/slides/build_semantic_uc.mjs`。验证器不覆盖已有交付文件。
4. 草稿和验证输出留在 `tmp/ppt_uc/`。检查全部页面后，使用 PowerPoint 导出 PDF。

图表数据保留 12 位有效数字以兼容内嵌 Excel 工作簿，展示的百分比与源证据保持相同精度。完整精度保留在原始 JSON。
