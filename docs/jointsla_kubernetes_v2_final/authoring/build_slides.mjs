import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
const ROOT=process.cwd(), B=path.join(ROOT,'.cache/publication_v2_build'), O=path.join(ROOT,'docs/jointsla_kubernetes_v2_final');
const SKILL='C:/Users/dioni/.codex/plugins/cache/openai-primary-runtime/presentations/26.1007.11041/skills/presentations';
const PY='C:/Users/dioni/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const C=JSON.parse(await fs.readFile(path.join(O,'canonical_results.json'),'utf8'));
const P=Object.fromEntries(C.policies.map(x=>[x.policy,x]));const F=x=>Number(x).toFixed(2);
const pres=Presentation.create({slideSize:{width:1280,height:720}});
const colors=['#7F8896','#C9823B','#5478AE','#147F6C','#70A89B','#916B9C'];
const source='Source: frozen Kubernetes comparison v2, 30 paired blocks, 180 trials, 230400 offered outcomes. canonical_results.json and tables/*.csv in the final research package.';
function txt(s,text,x,y,w,h,size=25,bold=false,color='#17242D') {
 const t=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 t.text=text;t.text.style={typeface:'Arial',fontSize:size,bold,color};t.text.insets=0;return t;
}
function slide(title,notes=source){const s=pres.slides.add();s.background.fill='#FFFFFF';txt(s,title,65,48,1150,95,43,true);txt(s,'JointSLA   Kubernetes comparison v2',65,676,850,24,16,false,'#64727C');txt(s,String(pres.slides.items.length).padStart(2,'0'),1170,676,50,24,16,false,'#64727C');s.speakerNotes.text=notes;return s;}
function table(s,values,x,y,w,h,widths){const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});t.borders.assign({fill:'#D7DFE5',width:1,style:'solid'});for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){let a=t.getCell(r,c);a.fill=r===0?'#DDE6ED':r%2===0?'#F5F7F9':'#FFFFFF';a.text.style={typeface:'Arial',fontSize:22,bold:r===0,color:'#17242D'};}return t;}
function bar(s,arms,metric,x,y,w,h,max,title,series){const chart=s.charts.add('bar',{position:{left:x,top:y,width:w,height:h},categories:arms.map(a=>({static:'Static-2',reactive:'Reactive',hpa:'Native HPA',joint:'JointSLA',joint_sq:'Joint scaler / SQ',reactive_joint:'Reactive / Joint router'}[a])),series:series?.map(a=>({...a,values:a.values.map(v=>Number(v.toFixed(6)))}))??[{name:title,values:arms.map(a=>Number(P[a][metric+'_mean'].toFixed(6))),fill:colors[3],points:arms.map((a,i)=>({idx:i,fill:colors[Object.keys(P).indexOf(a)]}))}],hasLegend:!!series,legend:{position:'bottom',textStyle:{fontSize:18}},barOptions:{direction:'column',grouping:'clustered',gapWidth:100},chartFill:'#FFFFFF',plotAreaFill:'#FFFFFF',dataLabels:{showValue:!series,position:'outEnd',numberFormatCode:'0.00',textStyle:{fontSize:20,fill:'#17242D'}},xAxis:{textStyle:{fontSize:18},line:{fill:'#98A5AF',width:1}},yAxis:{min:0,max,majorUnit:max/5,title:{text:title,textStyle:{fontSize:20}},textStyle:{fontSize:18},majorGridlines:{fill:'#E0E6EB',width:1},numberFormatCode:'0'}});applyPresentationChartFont(chart,{fontFamily:'Arial'});return chart;}
let s=slide('JointSLA for Kubernetes inference');
txt(s,'Deadline-aware routing and warm replica headroom',65,210,1110,150,56,true);
txt(s,'Completed comparison v2\n30 paired blocks  /  180 trials  /  230,400 outcomes',65,400,1110,100,28);
txt(s,'Lower SLA failures with higher replica-time cost',65,528,1110,70,31,true,'#147F6C');txt(s,'9 October 2026',65,617,1000,30,21);
s=slide('The short-burst orchestration problem');
txt(s,'Strict deadlines under sudden load',65,180,535,65,32,true);txt(s,'Queues can fill before new replicas become ready.\n\nCPU metric collection and pod warm-up operate on different timescales from request deadlines.',65,265,535,270,28);
txt(s,'The evaluation question',710,180,500,65,32,true);txt(s,'Does joint routing and replica headroom reduce all-offered failures?\n\nWhat additional replica-time does that reduction require?',710,265,500,270,28);
txt(s,'SLA failures include late completions and rejected requests.',65,595,1140,50,26,true);
s=slide('The research and runtime architecture',source+' Architecture: JOINTSLA_FINAL_REPORT.md and INFRASTRUCTURE_VALIDATION.md. Simulator sources remain frozen.');
txt(s,'Frozen research simulator',65,175,440,55,31,true);txt(s,'CPU/GPU capacity, queues and placement\nSeparate simulation experiments',65,240,475,110,25);
txt(s,'Real Kubernetes inference',675,175,520,55,31,true);txt(s,'Client calls the gateway\nGateway runs unchanged JointSLA functions\nReady pods execute MobileNetV3-Large\nDeployment applies bounded scale changes',675,240,535,240,25);
txt(s,'Shared policy functions',65,415,480,55,31,true);txt(s,'joint_routing.router.choose\njoint_sla_v2.policy.required_warm',65,490,520,100,25);
txt(s,'Prometheus and Grafana observe the runtime.\nOne host, one virtual node, CPU execution.',675,525,540,100,25,true);
s=slide('JointSLA routing and warm headroom',source+' Frozen implementation: joint_sla_v2/policy.py and joint_routing/router.py. Risk is a proxy, not a calibrated probability.');
txt(s,'Replica demand',65,175,540,60,32,true);txt(s,'Recent arrivals and queued work\nMeasured serial service cycle\nDeadline slack and cold allowance',65,255,540,165,27);
txt(s,'Gold control floor 2, cap 4\nMultiplier 1.5, cold allowance 10 s\nDecisions every 2 s, cooldown 30 s',65,458,540,160,26,true,'#147F6C');
txt(s,'Request routing',710,175,495,60,32,true);txt(s,'Ready non-terminating pods only\nEstimate completion and deadline slack\nRank by variance-based risk and slack\nDeterministic tie breaking',710,255,495,215,27);txt(s,'Causal observed-state heuristic\nNo learned control component',710,535,495,95,27,true);
s=slide('The local Kubernetes prototype');
table(s,[['Component','CPU request / limit','RAM request / limit'],['Inference','500m / 1 core','1 / 2 GiB'],['Gateway','100m / 1 core','256 / 512 MiB']],65,170,1140,180,[330,400,410]);
txt(s,'Warm-up gates readiness. SIGTERM withdraws admission and drains work and responses.\nDeployment replacement and gateway restart provide local recovery.',65,398,1140,115,27);
txt(s,'306 tests and 1,420 outcomes in the infrastructure audit\n330 tests in the later retained comparison pre-run validation',65,550,1140,90,25,true);
s.speakerNotes.text=source+' Infrastructure audit is historical and excluded from v2. 75s grace, 60s bounded drain, 2s preStop. Operationally complete within audited local boundary, not production HA. Historical audit counts must not be pooled with main outcomes.';
s=slide('The registered experimental protocol');
txt(s,'30 paired blocks, seeds 1001–1030\n1,280 requests per arm at 120 requests/s\nConcurrency 32, approximately 10.7 s',65,170,540,160,28,true);
txt(s,'Gold 200 ms  /  Silver 400 ms  /  Bronze 800 ms\nSame tensors and deadlines within each block\nBalanced randomized serial order',65,365,540,170,25);
txt(s,'Six arms',710,170,500,55,32,true);txt(s,'Static-2 with round-robin\nReactive with shortest queue\nNative HPA with shortest queue\nJointSLA\nJoint scaler with shortest queue\nReactive scaler with Joint router',710,247,500,330,27);
txt(s,'Fresh policy process, two ready idle replicas, fixed preconditioning and settle.',65,605,1140,46,24,true);
s.speakerNotes.text=source+' Workload is deterministic paced Kubernetes burst, not compound Poisson simulator traffic. Order seed39107, eight preconditioning requests/backend, 35s settle, 20s follow-up. HPA sole actuator. Main sources/images/tapes frozen. User pause affected one exploratory arm before burst, retained and disclosed.';
s=slide('JointSLA lowers all-offered SLA failures');
bar(s,['static','reactive','hpa','joint'],'sla_failure_percent',65,170,1140,415,100,'SLA failure rate (%)');
txt(s,'49.89% for JointSLA versus 61.43% reactive, 61.50% static and 62.39% HPA',65,603,1140,48,24,true);
s.speakerNotes.text=source+' Native chart shows means only. Sample SD: Joint8.12, reactive6.94, static7.85, HPA7.37 percentage points. All-offered denominator includes every non200 plus completed late. Target below15% remains unmet.';
s=slide('Paired statistical evidence');
table(s,[['JointSLA minus','Difference pp','95% paired interval','Holm p'],...C.paired_sla.slice(0,3).map(x=>[x.comparison.replace('joint minus ',''),F(x.sla_failure_difference_pp),`[${F(x.ci95_low_pp)}, ${F(x.ci95_high_pp)}]`,x.holm_three_core_comparisons_p.toExponential(3)])],65,175,1140,280,[270,220,360,290]);
txt(s,'30 paired block differences, 10,000 bootstrap resamples\nTwo-sided Wilcoxon with Pratt zeros\nHolm correction across three core comparisons',65,495,1140,125,27);
s.speakerNotes.text=source+' Bootstrap seed39108. Reactive is primary; static/HPA secondary core. Intervals are pointwise percentile paired block bootstrap. Requests are not independent replications. CI and p copied exactly from frozen paired_comparisons.csv before display rounding.';
s=slide('Completed latency and HTTP rejection');
bar(s,['reactive','joint'],'p95_completed_latency_ms',65,185,545,365,400,'Completed p95 (ms)');bar(s,['reactive','joint'],'rejection_percent',670,185,545,365,60,'HTTP 503 (%)');
txt(s,'Latency excludes rejected requests.\nNo confirmatory p95 superiority claim.',65,585,1140,72,27,true);
s.speakerNotes.text=source+' Means±sampleSD: p95 Joint318.63±47.74ms reactive322.85±55.60ms. HTTP503 Joint33.98±7.75%, reactive43.16±7.48%. Native charts show means. All main rejected requests explicitly queue_full. Primary tests concern SLA failures.';
s=slide('Gold deadlines remain difficult');
bar(s,['static','reactive','hpa','joint'],'',65,170,1140,415,100,'Tier SLA failure rate (%)',['gold','silver','bronze'].map((tier,i)=>({name:tier[0].toUpperCase()+tier.slice(1),values:['static','reactive','hpa','joint'].map(a=>P[a][tier+'_sla_failure_percent_mean']),fill:['#C69535','#889DAE','#AC7652'][i]})));
txt(s,'JointSLA: Gold 79.63%, Silver 35.94%, Bronze 34.06% failures',65,604,1140,48,27,true);
s.speakerNotes.text=source+' Chart shows mean tier rates. Gold12810offered10201failed,Silver12810offered4604failed,Bronze12780offered4353failed. Deadlines200/400/800ms; shared FIFO inference admission. Does not establish robust Gold protection. Request failure categories retained separately.';
s=slide('Lower failures use more replica-time');
bar(s,['static','reactive','hpa','joint'],'target_replica_seconds',65,185,745,365,140,'Target replica-seconds');
txt(s,'103.45 versus 65.12',855,215,350,65,31,true,'#147F6C');txt(s,'58.84% more than reactive\n\n38.32 additional replica s\n95% descriptive interval\n[33.37, 43.38]',855,304,350,225,26);
txt(s,'The data does not establish greater resource efficiency.',65,604,1140,48,28,true);
s.speakerNotes.text=source+' Descriptive resource bootstrap10000 seed271830. Ratio of policy means. TargetRS covers burst to lastresponse+20s includes pending replicas, not actualCPUenergybill. JointreadyRS97.33,reactive63.29. Performance-v-cost scatter in figures/07_performance_cost. No static4/matchedbudgetarm. JointextraRS/on-time gain0.259461.';
s=slide('Ablations do not isolate a router gain');
bar(s,['joint','joint_sq','reactive_joint'],'sla_failure_percent',65,185,635,365,100,'SLA failures (%)');
txt(s,'Routing replacement',745,190,460,55,30,true);txt(s,'−2.10 pp  [−4.84, +0.73]\nRaw exploratory p = 0.158844\nInterval crosses zero',745,260,460,135,25);
txt(s,'Scaling replacement',745,432,460,55,30,true);txt(s,'−11.05 pp  [−13.73, −8.30]\nRaw p = 3.147870e−07',745,502,460,95,25);
txt(s,'Feedback changes realized replica trajectories in both mechanism arms.',65,613,1140,40,24,true);
s.speakerNotes.text=source+' Compared with Joint scaler/SQ and reactive/Jointrouter. Mechanism comparisons exploratory outsideHolmfamily. Scalingresultconsistentwithheadroomcontribution,notuniquepartitionofcausalbenefit. JointSQtargetRS112.84reactiveJoint65.44. FirstblockjointSQhad91.65minpausebeforeburst,retainedwithdisclosure.';
s=slide('Scope and limitations');
txt(s,'One CPU model, one physical host and one virtual Kubernetes node\nSynthetic tensors, shared capacity and uncontrolled host activity',65,178,1140,112,28);
txt(s,'Short paced burst with native HPA timing defaults\nNo matched-budget or static-four comparator',65,334,1140,112,28);
txt(s,'Historical simulation and integration audits remain separate\nOne exploratory preparation interval includes a user pause',65,490,1140,112,28);
s.speakerNotes.text=source+' Simulationheldout10nodes40services100slots100ms180simulations3046965outcomes overallcriterionfailed. Historical38.828125%497/1280vs47.265625%605/1280differentrevision/startstate,excluded. Userpause5498.868465sbeforefirstjointSQburst,noofferedduringpause. No physicalGPU,6Gdataplane,accuracyorproductionHAvalidation. ConservativefocusedrelatedworkInferLinehttps://arxiv.org/abs/1812.01776v2 INFaaShttps://www.usenix.org/conference/atc21/presentation/romero Clockworkhttps://www.usenix.org/conference/osdi20/presentation/gujarati .';
s=slide('Conclusion');
txt(s,'JointSLA significantly reduces SLA failures',65,190,1140,65,39,true,'#147F6C');txt(s,'The reduction requires more target replica-seconds than the main baselines.',65,290,1140,105,31);
txt(s,'The local prototype is operationally complete within its audited boundary.\nThe below-15% failure goal remains unmet.',65,438,1140,118,28);
txt(s,'Contribution: a controlled empirical comparison and reproducible trade-off evidence',65,602,1140,55,25,true);
s.speakerNotes.text=source+' No firsteverSLAautoscaling/routingnoveltyclaim, no greaterresourceefficiencyclaim. FocusedprimarypriorworkInferLine1812.01776v2,INFaaSATC2021,ClockworkOSDI2020. Reportsandtablesexplainconservativecontributionandremainingvenue/authorshipdetails.';
await fs.mkdir(path.join(B,'slides'),{recursive:true});
for(let i=0;i<pres.slides.items.length;i++){let png=await pres.export({slide:pres.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(B,'slides',`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));}
const candidate=path.join(B,'candidate.pptx');await(await PresentationFile.exportPptx(pres)).save(candidate);
console.log('Rendered and exported',pres.slides.items.length,'slides');
const result=await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath:path.join(O,'JointSLA_Conference_Presentation.pptx'),pythonExecutable:PY,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','5','--require-native-table-slide','8'],explicitTotalSlideCount:14,requiredNativeChartOwnerSlides:[7,9,10,11,12],requiredNativeTableOwnerSlides:[5,8],fontPolicy:{basis:'design',families:['Arial']},materializeLiteralChartWorkbooks:true,verifyArtifactToolImport:true,receiptPath:path.join(B,'deck.validation.json')});console.log(JSON.stringify(result));



