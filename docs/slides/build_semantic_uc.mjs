// Rebuild with the bundled @oai/artifact-tool runtime. See README.md in this folder.
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { Presentation, PresentationFile } from '@oai/artifact-tool';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const BUILD = path.join(ROOT, 'tmp/ppt_uc');
const OUT = path.join(ROOT, 'docs/slides');
const SKILL = process.env.PRESENTATIONS_SKILL_DIR;
if (!SKILL) throw new Error('Set PRESENTATIONS_SKILL_DIR to the installed Presentations skill directory.');
const { finalizePresentation, applyPresentationChartFont } = await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const data = JSON.parse(await fs.readFile(path.join(ROOT,'artifacts/semantic_uc/summary.json'),'utf8'));
const example = JSON.parse(await fs.readFile(path.join(ROOT,'artifacts/semantic_uc/example.json'),'utf8'));
const M=data.confirmation.metrics;
const C={navy:'#102B3F',teal:'#007F86',blue:'#3878A5',muted:'#566A78',gray:'#A7B5C0',ink:'#183244',light:'#F5F8FA',white:'#FFFFFF',orange:'#B86128',line:'#D8E1E7'};
const FONT='Microsoft YaHei';
const BASE='https://github.com/qinyishcn/jev-rrc-optimization/blob/2d82463f8fa5b988bb3f16aaed3a25ecf1d3cb7d';
const PPT=Presentation.create({slideSize:{width:1280,height:720}});
const manifest=[];
const pct=(v,d=4)=>(100*v).toFixed(d)+'%';
const chartOwners=[];const tableOwners=[];

function text(s,txt,x,y,w,h,size=28,color=C.ink,bold=false){
  const sh=s.shapes.add({geometry:'textbox',name:'text-'+s.shapes.items.length,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  sh.text=txt;sh.text.style={typeface:FONT,fontSize:size,color,bold,autoFit:'none'};
  return sh;
}
function slide(title,sub,notes='',dark=false){
  const s=PPT.slides.add();s.background.fill=dark?C.navy:C.light;
  const n=PPT.slides.items.length;
  if(title)text(s,title,64,46,1152,64,44,dark?C.white:C.navy,true);
  if(sub)text(s,sub,66,126,1148,54,25,dark?'#C8DBE6':C.muted);
  text(s,String(n).padStart(2,'0'),1164,670,50,30,18,dark?'#8CA8B8':C.muted);
  s.speakerNotes.textFrame.setText(notes+'\n\n证据快照：2026-10-08。PPT 编制：2026-10-09。\n'+BASE+'/docs/rrc_cause_semantic_uc.md\n'+BASE+'/artifacts/semantic_uc/summary.json');
  manifest.push({slide:n,title,subtitle:sub,notes});return s;
}
function foot(s,txt){text(s,txt,66,637,1080,45,19,C.muted);}
function table(s,values,x,y,w,h,widths,highlight=-1,font=25){
  const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});
  t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({textStyle:{typeface:FONT,fontSize:font,color:C.ink},fill:C.white,margins:{left:14,right:10,top:9,bottom:8}});
  t.borders.assign({fill:C.line,width:0.7,style:'solid'});
  t.cells.block({row:0,column:0,rowCount:1,columnCount:values[0].length}).assign({fill:C.navy,textStyle:{color:C.white,bold:true,typeface:FONT,fontSize:font}});
  if(highlight>0)t.cells.block({row:highlight,column:0,rowCount:1,columnCount:values[0].length}).assign({fill:'#E3F2F1',textStyle:{color:C.teal,bold:true}});
  tableOwners.push(PPT.slides.items.length);return t;
}
function chart(s,type,config){
  // Chart workbooks use at most 12 significant digits; displayed rates remain unchanged.
  for(const series of config.series ?? [])series.values=series.values.map(v=>Number(v.toPrecision(12)));
  // The facade uses xAxis for categories and yAxis for values even on a horizontal bar.
  if(config.barOptions?.direction==='bar'){
    [config.xAxis,config.yAxis]=[config.yAxis,config.xAxis];
    config.yAxis.majorUnit=0.001;
    config.yAxis.visible=false; // Exact labels on each bar supply the values and percent unit.
  }
  if(type==='line')config.lineOptions={smooth:false};
  const c=s.charts.add(type,{chartFill:C.light,chartLine:{fill:'none',width:0},plotAreaFill:C.light,plotAreaLine:{fill:'none',width:0},...config});
  applyPresentationChartFont(c,{fontFamily:FONT});chartOwners.push(PPT.slides.items.length);return c;
}
function statement(s,label,body,y){text(s,label,68,y,325,48,29,C.teal,true);text(s,body,410,y,800,100,28);}

// 1. A minimal cover, with the scope adjacent to the headline.
{
const s=slide('','', '研究对象是开源 Decider 2B v11。闭源 Jev 未参与测试。正向结果来自业务语义到冻结策略的流水线。',true);
text(s,'业务语义辅助\nRRC 配置优化',70,166,1140,220,76,C.white,true);
text(s,'Decider 在 AGV 穿越与边界巡检场景中的验证',75,425,1120,56,34,'#BEE7E6');
text(s,'LTE A3 系统仿真 · 研究进展',77,548,1100,44,24,'#C8DBE6');
text(s,'2026.10.09',77,600,1000,34,22,'#8CA8B8');
}
// 2. Motivation and the specific information gap.
{
const s=slide('研究背景：瞬时运动相同，后续任务不同','AGV（Automated Guided Vehicle，自动导引运输车）的小区边界移动',
'AGV = Automated Guided Vehicle。RRC = Radio Resource Control，无线资源控制。这里只研究 LTE Event A3 的切换参数。既有可靠结构化路线接口优先于文本模型。参考论文 https://arxiv.org/abs/2505.16821 是 LLM RRC 仿真相关工作，不构成本项目参数优化成功的证据。');
text(s,'RRC：Radio Resource Control，无线资源控制',68,208,1080,48,32,C.teal,true);
text(s,'同一位置、同一速度、同一无线环境\n仅靠瞬时数值，难以区分未来路线',68,278,1100,100,32);
table(s,[['调度任务','未来运动','适合的切换倾向'],['驶往包装工位','一次穿越后继续前进','及时完成必要切换'],['边界往返巡检','短距离往返、反复跨界','抑制频繁来回切换']],68,414,1136,180,[310,440,386],-1,26);
foot(s,'应用前提：上游提供非结构化调度说明，且缺少可靠的结构化路线接口。');
}
// 3. A native data chart derived from the specified trajectories.
{
const s=slide('A3 切换中的及时性与稳定性','邻区信号优势持续满足条件后，传统 RRC 流程触发切换',
'H 为迟滞裕量，单位 dB。TTT = Time-to-Trigger，触发等待时间，单位 ms。RSRP = Reference Signal Received Power，参考信号接收功率。图由 g1 预设轨迹规则计算，展示前 8 秒，非新增测量。跨区轨迹 x=-8+8t，巡检每 2 秒反向，x 范围 [-8,8]。H0/T0 仍经过测量报告与 RRC 信令。');
const times=Array.from({length:9},(_,i)=>i);
chart(s,'line',{position:{left:60,top:204,width:730,height:390},categories:times.map(String),series:[{name:'单向穿越',values:times.map(t=>-8+8*t),line:{fill:C.teal,width:3},marker:{symbol:'circle',size:5}},{name:'边界巡检',values:times.map(t=>{const q=t%4;return q<=2?-8+8*q:24-8*q;}),line:{fill:C.orange,width:3},marker:{symbol:'circle',size:5}},{name:'小区边界',values:times.map(()=>0),line:{fill:C.gray,width:1}}],hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:21}},xAxis:{title:'时间（s）',textStyle:{fontSize:19},majorGridlines:null},yAxis:{title:'相对边界位置（m）',min:-10,max:60,majorUnit:20,numberFormatCode:'0',textStyle:{fontSize:19},majorGridlines:{fill:C.line,width:1}},dataLabels:{showValue:false}});
text(s,'H：迟滞裕量',838,218,365,44,30,C.teal,true);
text(s,'邻区信号需领先多少',838,274,365,45,27);
text(s,'TTT：触发等待时间',838,360,365,44,30,C.teal,true);
text(s,'该条件需持续多久',838,416,365,45,27);
text(s,'更大的 H / TTT\n有利于过滤短暂跨界\n也可能推迟必要切换',838,505,365,100,24,C.muted);
foot(s,'图示为 g1 的预设运动轨迹。策略需要区分“持续穿越”与“短时往返”。');
}
// 4. A native table is the editable algorithm specification.
{
const s=slide('实现方法：语义识别与无线策略分工','Decider：Jev 类开源决策模型（2B），一次前向选择任务语义',
'Decider 是本项目采用的 Jev 类开源类型化决策模型，2B v11。输入包括白名单数值和原始调度文本。一次前向给两个合法语义候选打分，取最高分，未做新微调。无线策略通过校准集确定，测试前冻结。此处属于受限动作选择，不是自由生成任意 RRC 代码。'+BASE+'/system_validation/semantic_uc.py');
table(s,[['步骤','输入 / 操作','输出'],['1  任务识别','读取当前 AGV 的生效调度说明\n处理修订、否定与其他车辆干扰','穿越 或 巡检'],['2  冻结策略映射','使用校准集确定的条件策略\n测试时保持映射不变','合法 H / TTT'],['3  传统协议执行','按既有 A3 测量、报告、切换流程运行','逐包指标与切换次数']],68,208,1136,274,[235,580,321],-1,26);
text(s,'穿越：H = 0 dB，TTT = 0 ms',72,528,1080,44,31,C.teal,true);
text(s,'巡检：H = 1 dB，TTT = 80 ms',72,578,1080,44,31,C.teal,true);
foot(s,'每个会话开始前决策一次。传统 A3 执行切换，模型负责提供任务语义。');
}
// 5. Reproducible physics setup.
{
const s=slide('仿真配置：LTE 完整协议栈的 A3 切换','ns-3 3.46，LTE / EPC / X2，非理想 RRC 信令',
'EPC = Evolved Packet Core，LTE 核心网。X2 是基站间接口。两个基站、一个 UE（User Equipment，用户终端），RR 调度。固定传播环境，未设置变化衰落/阴影、多用户竞争。本次 UC 是 LTE A3，不是 NR DRX。'+BASE+'/system_validation/ns3_lte_handover.cc');
table(s,[['项目','配置'],['网络与运动','2 个基站、1 个 UE，初始连接西侧基站\n基站间距 250 / 300 / 375 m，速度 6 / 8 / 9 m/s'],['分组与时限','UDP 1200 B，每 1 ms 一包，9.6 Mbit/s\n截止时间 20 ms，每次发送 23,000 包'],['会话与决策','会话 24 s，仿真停止于 24.1 s\n流量从 1 s 发至 24 s，开始前推理 1 次'],['候选参数','H / TTT：0/0、1/80、2/160、3/256、6/320\n单位分别为 dB 和 ms']],68,205,1136,362,[260,876],-1,25);
foot(s,'高负载业务用于暴露切换成本，尚未按真实 AGV 控制报文校准。');
}
// 6. Make independence and shared information clear.
{
const s=slide('实验设计：冻结策略，再验证新语言样本','210 次真实仿真，文本变体复用相同物理结果',
'校准：6 物理场景 ×5 配置 ×2 随机运行（91、92）=60。测试：6×5×5（101–105）=150。确认集在 pilot 后、确认推理前冻结，24 新成对语言家族，每家族 2 条独立文本，共48条，乘3几何为144输入。TF-IDF 用32条独立先导文本训练，几何重复先去重。合成英文模板、未使用独立标注员。文本均衡设置穿越/巡检 50/50。');
statement(s,'物理校准', '6 个场景 × 5 档配置 × 2 个随机种子\n60 次仿真，冻结固定配置与条件映射',210);
statement(s,'物理测试', '相同 6 个场景，另用 5 个随机种子\n150 次仿真，所有方案共享随机条件',342);
statement(s,'语言确认集', '48 条新文本 × 3 种几何 = 144 个输入\nTF-IDF 词频特征 + 逻辑回归，以 32 条文本训练',474);
foot(s,'各文本方案可见相同输入。改写复用物理轨迹，不作为新增独立仿真或独立分组。');
}
// 7. Headline outcome, chart values read directly from the saved evidence.
{
const gain=1-M.decider.deadline_miss_rate/M.tfidf.deadline_miss_rate;
const s=slide('确认结果：相对同文本传统基线下降 74.5%','主指标：丢包 + 收到但超过 20 ms 的分组，占全部发送包的比例',
'默认选项顺序是主结果。TF-IDF（Term Frequency–Inverse Document Frequency，词频与逆文档频率）加逻辑回归识别文本意图，随后使用相同无线映射。传统结构化意图参考获得100%正确意图，不需要文本模型。图显示确认集复用物理结果的加权指标，不是对1656万独立新包的测量。');
const methods=['calibrated_fixed','tfidf','qwen_onepass','decider','known_intent'];
chart(s,'bar',{position:{left:58,top:218,width:840,height:380},categories:['校准固定','TF-IDF + 策略','Qwen 单次前向','Decider + 策略','已知结构化意图'],series:[{name:'超时/丢包率',values:methods.map(k=>M[k].deadline_miss_rate),fill:C.gray,points:methods.map((k,i)=>({idx:i,fill:k==='decider'?C.teal:k==='known_intent'?C.blue:C.gray})),valuesFormatCode:'0.0000%'}],barOptions:{direction:'bar',grouping:'clustered',gapWidth:65},hasLegend:false,xAxis:{visible:true,textStyle:{fontSize:20},numberFormatCode:'0.00%',min:0,max:0.004,majorGridlines:{fill:C.line,width:1}},yAxis:{textStyle:{fontSize:23},majorGridlines:null},dataLabels:{showValue:true,position:'outEnd',textStyle:{fontSize:22,bold:true,fill:C.navy}}});
text(s,(gain*100).toFixed(1)+'%',930,239,280,100,67,C.teal,true);
text(s,'相对 TF-IDF 下降',932,350,280,70,26);
text(s,'0.2391%\n降至 0.0610%',934,445,275,120,34,C.navy,true);
foot(s,'正确结构化意图参考为 0.0500%，仍优于 Decider。Qwen 的统计比较见下一页。');
}
// 8. Claims and uncertainty, native evidence table.
{
const s=slide('增益分析：信息价值与语义识别能力','差值为 Decider 超时/丢包率减基线，负值表示 Decider 更好',
'95%区间按成对语言家族和共同随机运行做双轴 bootstrap，10,000 次，三种几何固定。单位为百分点，不是相对百分比。区间未包含跨工厂、真实业务或不同传播条件的不确定性。Qwen默认顺序的区间上界为0，不能声明稳定显著优势。');
const comp=data.confirmation.comparisons_decider_minus_baseline;
const row=(name,key)=>[name,(100*comp[key].difference).toFixed(4),comp[key].ci95.map(x=>(100*x).toFixed(4)).join(' 至 ')];
table(s,[['比较基线','差值（百分点）','95% 成对置信区间'],row('校准固定，无任务文本','calibrated_fixed'),row('TF-IDF，同任务文本','tfidf'),row('Qwen，单次前向','qwen_onepass')],68,212,1136,238,[440,260,436],-1,26);
text(s,'相对固定配置',72,490,340,44,29,C.teal,true);
text(s,'增加了未来任务先验，改善路线不可辨识问题',440,490,760,60,28);
text(s,'相对同文本 TF-IDF',72,564,350,44,29,C.teal,true);
text(s,'体现少标注条件下的语义识别收益',440,564,760,60,28);
foot(s,'Qwen 默认顺序的区间触及 0，目前只能报告更低的点估计。');
}
// 9. Self-contained input specification for one concrete example.
{
const s=slide('完整输入样例：驶往包装工位','同一数值观测下，调度文本提供后续运动先验',
'样例 test_7_1_cross，g1，测试随机运行101。原始模型输入只有下列白名单字段和dispatch_text。字段名、原始问句、候选、概率及全部配置结果见example.json。这里为完整9字段，不含真实未来轨迹、标签、场景ID、随机种子或结果。'+BASE+'/artifacts/semantic_uc/example.json');
table(s,[['输入字段','值','含义'],['initial_x_m / initial_velocity_mps','−8 m / +8 m/s','距边界位置 / 向东速度'],['cell_spacing_m / initial_serving_cell','300 m / west','基站间距 / 初始服务小区'],['packet_interval_ms / packet_bytes','1 ms / 1200 B','分组间隔 / 分组长度'],['deadline_ms / session_duration_s','20 ms / 24 s','分组截止时间 / 会话长度']],68,197,1136,247,[575,230,331],-1,22);
text(s,'dispatch_text：原始调度说明',70,477,1130,38,26,C.teal,true);
text(s,'“Advance into the other cell toward packaging.\nThe itinerary includes no turnaround in this area.”',70,524,1130,76,26);
foot(s,'中文释义：进入另一小区前往包装区，在这一区域不掉头。其余结果字段不进入推理。');
}
// 10. A paired counterfactual demonstrating the mechanism.
{
const s=slide('配对样例：只改变调度文本，策略随之改变','g1、随机运行 101，每个会话发送 23,000 包',
'跨区文本和全部数值在上一页。巡检原文：Oscillate between the near-side and far-side markers; neither endpoint is a final destination. 两例全部数值相同。Decider穿越概率0.997809、巡检概率0.997688。穿越的TF-IDF将no turnaround误判为巡检。巡检H2/T160等也零违约，多档并列，不能把该例解释为唯一最优。两例均来自先导测试，不是确认集汇总。'+BASE+'/artifacts/semantic_uc/example.json');
table(s,[['任务与方案','输出 H / TTT','超时/丢包','收到包 P99','切换次数'],['穿越 · 固定 / TF-IDF','1 dB / 80 ms','381（1.6565%）','62 ms','1'],['穿越 · 直接配置 Decider','2 dB / 160 ms','691（3.0043%）','82 ms','1'],['穿越 · 语义 Decider / Qwen','0 dB / 0 ms','23（0.1000%）','5 ms','1'],['巡检 · 沿用激进配置','0 dB / 0 ms','287（1.2478%）','13 ms','12'],['巡检 · 语义 Decider','1 dB / 80 ms','0（0%）','5 ms','0']],68,206,1136,327,[400,200,245,175,116],-1,23);
text(s,'穿越：避免切换过迟',72,563,520,48,30,C.teal,true);
text(s,'巡检：避免频繁来回切换',652,563,560,48,30,C.teal,true);
foot(s,'巡检文本表示在两侧标记点间往返。穿越样例中的 Qwen 指已保存的生成/单次前向对照。');
}
// 11. Separate output-format speed from task-performance evidence.
{
const s=slide('Qwen 对照：顺序稳健性比速度差异更突出','Qwen3.5-2B-Base 使用相同输入、语义候选和冻结策略',
'确认集原序/反序准确率：Decider141/144、144/144，Qwen单次前向132/144、91/144。反序指两个语义选项交换。确认时延：RTX3070 8GB，bf16、batch1、eager、8 CPU线程，加载排除，至少3次预热，计时包含相同额外CPU tokenization，顺序执行，非随机交错重复测量。pilot同提示生成Qwen1057.75985ms vs Decider167.87475ms约6.3倍，主要由自回归和单前向的方式差异造成。TF-IDF CPU P50约0.63ms。');
chart(s,'bar',{position:{left:65,top:213,width:660,height:350},categories:['Decider','Qwen 单次前向'],series:[{name:'默认顺序',values:[M.decider.intent_accuracy,M.qwen_onepass.intent_accuracy],fill:C.teal,valuesFormatCode:'0.0%'},{name:'交换顺序',values:[M.decider_reversed.intent_accuracy,M.qwen_onepass_reversed.intent_accuracy],fill:C.gray,valuesFormatCode:'0.0%'}],barOptions:{direction:'column',grouping:'clustered',gapWidth:100},hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:21}},xAxis:{textStyle:{fontSize:23}},yAxis:{min:0,max:1.15,numberFormatCode:'0%',textStyle:{fontSize:20},majorGridlines:{fill:C.line,width:1}},dataLabels:{showValue:true,position:'outEnd',textStyle:{fontSize:21,bold:true}}});
table(s,[['确认集推理时延','P50 / P95'],['Decider','183.5 / 210.6 ms'],['Qwen 单次前向','192.0 / 233.4 ms']],756,230,448,210,[220,228],-1,23);
text(s,'同为单次前向时\n中位速度仅约 1.05 倍',765,484,440,85,29,C.teal,true);
foot(s,'先导集对生成式 Qwen 约快 6.3 倍，主要来自推理方式。CPU TF-IDF 约 0.6 ms。');
}
// 12. Evidence-based explanation for the original negative result.
{
const s=slide('直接数值配置缺少增益的原因','现有消融支持接口与训练问题，不能据此断言模型内部缺少无线知识',
'基础Decider直接输出H2/T160，循环旋转五档选项60/60保持H2，可排除该测试中的简单位置偏好。上下文142–231token低于1536 cap，没有截断。清晰语义表示使路线识别12/24到24/24，直接配置仍无条件变化。旧LoRA32场景、2epoch、gradacc4，共16optimizer updates、208896 q/v训练参数，5种顺序0/12场景动作稳定。旧实验强规则已接近候选集上限，部分候选KPI并列，单一分类标签不等价于最小网络损失。');
statement(s,'输入表达与动作映射', '更清晰的表达改善路线识别\n直接五档配置仍倾向固定 H2 / T160',209);
statement(s,'领域微调不足', '旧 A3 LoRA 仅 16 次优化更新\n固定选项顺序训练后存在顺序敏感',340);
statement(s,'基线与目标约束', '强规则已接近有限候选集的可达上限\n并列最优配置让单标签训练偏离网络损失',472);
foot(s,'新 UC 使用基础 Decider。改善来自“语义识别 + 校准映射”的分工，未做新微调。');
}
// 13. Explicit bounded claim and a real model error.
{
const s=slide('当前边界与一个明确失败样例','确认集的 3 个 Decider 错误来自同一文本在 3 种几何下的重复',
'错误文本confirm_22_*_cross：This AGV has a terminal eastward route. Another AGV handles the recurring boundary patrol. 默认顺序将另一辆车的巡检任务归给当前车辆。交换选项后修正，不能事后挑选100%反序结果作为主结果。训练和确认英文模板均由研究者手写。物理运动、50/50类别比例、高负载、固定传播、单UE是受限条件。当前约184ms预决策不能放进20ms逐包闭环。');
text(s,'“This AGV has a terminal eastward route.\nAnother AGV handles the recurring boundary patrol.”',70,210,1130,105,32,C.navy,true);
text(s,'误判原因：把另一辆 AGV 的巡检任务绑定到当前车辆',72,345,1100,52,31,C.orange,true);
text(s,'适用范围',72,450,300,42,28,C.teal,true);
text(s,'合成英文任务、单 UE、固定传播、已知巡检轨迹',390,450,810,75,28);
text(s,'实时性范围',72,551,300,42,28,C.teal,true);
text(s,'会话前约 184 ms 决策，需要足够规划提前量',390,551,810,75,28);
foot(s,'LTE 软件系统仿真尚不能证明真实 RF、NR 或商用紧时延业务的可靠性。');
}
// 14. Concrete future experiments and their acceptance conditions.
{
const s=slide('Future work：真实调度与无线闭环验证','下一阶段以同信息、强基线、完整成本的盲测为判据',
'方案来自既有研究计划docs/rrc_cause_semantic_uc.md及next_validation.md。以下为尚未执行的计划。优先验证应用前提，若已有可靠结构化路线接口，直接用传统控制器。需要按工厂/车辆/模板划分独立测试，冻结策略后随机交错控制器。记录推理、配置下发、生效失败、切换中断、包期限、信令/资源成本。');
table(s,[['优先级','下一步实验','通过条件'],['P0  真实任务接口','真实调度文本、车辆 ID、任务版本\n地图与轨迹日志，跨模板盲测','比结构化路线接口与\n充分训练的轻量分类器更有价值'],['P1  不确定执行','调度修订、轨迹偏离、多主体干扰\n加入观测冲突与保守回退','收益在执行误差下保持\n置信度能够支持安全回退'],['P2  无线系统扩展','多 UE、衰落/遮挡、负载变化\n随后接实际协议栈和无线闭环','纳入推理与配置下发成本后\n仍降低约束违约或综合成本']],68,209,1136,332,[230,480,426],-1,25);
text(s,'若完整成本下增益消失，应否定该系统需要 Decider 的假设',72,581,1125,50,29,C.teal,true);
}
// 15. Conclusion retains both the positive finding and its comparator.
{
const s=slide('结论：语义先验可以改善受限 RRC 决策','最有潜力的场景：少标签、调度表述多变、缺少结构化路线接口',
'主结论严格对应确认集默认顺序。相对固定配置下降80.6%，相对同文本TF-IDF下降74.5%。正确结构化意图控制器0.05%更好。Qwen默认序差值95%区间触0，速度相对onepass仅1.05倍。当前证据支持非结构化语义接口的价值，不支持模型已优于可靠结构化传统控制器。');
text(s,'74.5%',72,210,1110,120,88,C.teal,true);
text(s,'相对同文本 TF-IDF，超时/丢包率下降',77,350,1100,58,36,C.navy,true);
text(s,'Decider 识别生效任务，校准策略提供无线参数',77,450,1110,52,32);
text(s,'已有正确结构化意图时，传统控制器仍更好\n真实系统增益取决于任务接口、执行误差与完整开销',77,534,1110,98,29,C.muted);
}
// 16. Full comparison for readers to audit the headline claim.
{
const s=slide('附录：确认集性能与证据入口','默认选项顺序。所有文本分类方案共用相同的意图到参数映射',
'P99为每个场景的收到包P99的均值，不是全体包混合P99，丢失包不进入P99。超时/丢包率包含lost与late_received。平均切换次数为每会话。准确率是144输入中的比率，只有48独立文本，跨几何重复不独立。关键词改进版52.08%、0.5282%，原关键词43.75%、0.6471%。表中保留改进版作为传统解析的补充，不以其作为主增益基线。');
const keys=['calibrated_fixed','improved_keyword','tfidf','qwen_onepass','decider','known_intent'];
const names=['校准固定','改进关键词','TF-IDF + 策略','Qwen 单次前向','Decider + 策略','已知结构化意图'];
const rows=keys.map((k,i)=>[names[i],M[k].intent_accuracy===undefined?'—':pct(M[k].intent_accuracy,2),pct(M[k].deadline_miss_rate),pct(M[k].lost/M[k].sent),M[k].mean_of_case_p99_delay_ms.toFixed(2),M[k].mean_handovers_per_session.toFixed(2)]);
table(s,[['方案','意图准确率','超时/丢包率','丢包率','P99（ms）','切换/会话'],...rows],64,207,1152,330,[280,165,195,175,177,160],5,23);
text(s,'完整报告、原始输入输出与可复现代码',69,570,1120,36,26,C.teal,true);
text(s,'github.com/qinyishcn/jev-rrc-optimization',69,613,1100,40,25);
}

await fs.mkdir(BUILD,{recursive:true});await fs.mkdir(OUT,{recursive:true});
const draft=path.join(BUILD,'semantic_uc_candidate.pptx');
await (await PresentationFile.exportPptx(PPT)).save(draft);
await fs.writeFile(path.join(BUILD,'slide_content.json'),JSON.stringify(manifest,null,2));
const finalName=process.env.PPT_FINAL_NAME || 'semantic_rrc_uc_20261009_release.pptx';
const result=await finalizePresentation({workspaceDir:ROOT,candidatePath:draft,finalPath:path.join(OUT,finalName),pythonExecutable:process.env.RUNTIME_PYTHON,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit',...[...new Set(tableOwners)].flatMap(n=>['--require-native-table-slide',String(n)])],fontPolicy:{basis:'design',families:[FONT]},requiredNativeTableOwnerSlides:[...new Set(tableOwners)],requiredNativeChartOwnerSlides:[...new Set(chartOwners)],materializeLiteralChartWorkbooks:true,verifyArtifactToolImport:true,receiptPath:path.join(BUILD,finalName+'.validation.json')});
console.log(JSON.stringify({final:result,slides:manifest.length}));
