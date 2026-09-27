export const SYSTEMS=[{id:'explore',name:'探索',roles:['调研','观察','核验']},{id:'advise',name:'参谋',roles:['分析','决策','风险']},{id:'create',name:'创作',roles:['文稿创作','视觉媒体','软件原型','编辑审校']},{id:'connect',name:'连接',roles:['匹配','关系','协作']},{id:'execute',name:'执行',roles:['执行规划','操作','运行监督','结果验收']}];
// Stable IDs preserve provenance. Capabilities are loaded into a shared runner;
// they do not create persistent agents or copies of the user's memory.
const specs={
 'explore-0':{kind:'skill',trigger:'调研|检索|搜索|资料|竞品',purpose:'从授权资料中整理事实、案例与尚待核实的问题',steps:['界定问题与资料范围','逐项提取事实并标注来源','比较一致与冲突信息，列出资料缺口'],outputs:['问题与范围','发现与来源','未知与下一步'],checks:['事实与推断分开','来源能回到已提供资料'],limitations:'默认整理本人提供的资料；联网查找需从专用入口创建任务，配置支持 Responses 网页搜索的服务并单独确认。'},
 'explore-1':{kind:'monitor',trigger:'观察|跟踪|关注变化|定期',purpose:'比较已授权的状态快照，识别需要关注的变化',steps:['确认主题、基准和观察时间','比较所选快照，区分变化与缺少数据','给出需要后续处理的变化清单'],outputs:['观察范围','变化与证据','后续安排'],checks:['不把缺少数据写成没有变化','每个变化标明时间与来源'],limitations:'可分析所选快照；另有本人确认的周期联网检查，发现新增公开来源时提醒，受期限、次数与总额度限制；同一网页正文变化暂不自动识别。'},
 'explore-2':{kind:'check',trigger:'核验|验证|查证|事实检查',purpose:'逐项核对主张与提供的证据',steps:['拆出可核对主张','对照原始证据及反例','分别标记支持、矛盾或未知'],outputs:['待核对主张','证据核对','结论与未知'],checks:['缺证据时保持未知','模型评分不能当作事实证明'],review:'required'},
 'advise-0':{kind:'skill',trigger:'分析|原因|问题|拆解',purpose:'澄清目标、约束、假设和问题结构',steps:['重述需要解决的问题','区分事实、假设、约束','梳理因果与需验证的假设'],outputs:['问题定义','分析与假设','建议下一步'],checks:['不把相关性当因果','结论对应用户目标']},
 'advise-1':{kind:'skill',trigger:'决策|选择|比较|取舍|对比',purpose:'根据目标比较方案并说明取舍',steps:['列出可行选项与不行动选项','统一比较标准','解释选择条件和需要补充的依据'],outputs:['候选方案','比较与取舍','建议与条件'],checks:['包含代价与不确定性','不代替用户作最终承诺']},
 'advise-2':{kind:'check',trigger:'风险|失败路径|反例',purpose:'检查方案的失败路径与不确定性',steps:['识别可能失效的假设','按影响与证据列风险','给出缓解办法和停止条件'],outputs:['审查范围','风险与证据','应对与停止条件'],checks:['不编造概率','重要风险有证据或明确假设'],review:'required'},
 'create-0':{kind:'skill',trigger:'文稿|文案|写|文章|方案',purpose:'交付符合目标、语气与格式要求的文字成果',steps:['确认受众、用途和边界','形成完整可编辑文稿','检查事实来源与遗漏'],outputs:['正文','依据与待确认项'],checks:['符合用户原格式和排版约束','不虚构引用']},
 'create-1':{kind:'skill',trigger:'图片|视觉|海报|视频|音效',purpose:'准备视觉或媒体制作所需的创意和素材说明',steps:['确定尺寸、风格和信息层级','编写制作说明及素材需求','列出生成、编辑和交付检查项'],outputs:['创意与规格','制作说明','交付检查'],checks:['区分制作方案与实际生成的媒体','尊重参考设计'],limitations:'默认生成制作方案；专用入口可生成单张图片，需配置图片服务。视频及音频生成尚未接通。'},
 'create-2':{kind:'skill',trigger:'软件|代码|网页|应用|原型',purpose:'产出可审查的代码或交互原型',steps:['明确页面行为和输入输出','给出完整代码及使用方式','列出测试步骤、依赖与未验证部分'],outputs:['实现','使用与测试','限制与待验证'],checks:['未运行的测试必须标明','保留用户原设计约束'],review:'required',limitations:'可生成代码；Mini App 支持单文件网页预览，任意后端项目构建部署尚未接通。'},
 'create-3':{kind:'check',trigger:'编辑|审校|修改|校对|审稿',purpose:'对照需求、事实和风格审校成果',steps:['按原目标逐项检查','指出具体位置与改法','给出修订稿和需要用户确认的变化'],outputs:['问题清单','修订稿','待确认项'],checks:['不改变未授权的设计和含义','事实问题与表达偏好分开'],review:'required'},
 'connect-0':{kind:'skill',trigger:'匹配|找人|人选|招募',purpose:'从提供的候选中筛选适合的人或资源',steps:['确定需求和必要条件','按相同条件核对候选证据','列出匹配理由及未知项'],outputs:['匹配条件','候选与依据','待核实项'],checks:['不虚构候选人或联系方式','不读取对方私有资料'],limitations:'从已提供的候选资料匹配；外部人才和资源数据库尚未接通。'},
 'connect-1':{kind:'skill',trigger:'关系|沟通|回复|联系|开场|拒绝',purpose:'基于授权关系背景准备合适的表达',steps:['厘清本人想表达的意思与边界','只使用选择的对话和背景','提供可编辑草稿与语气选择'],outputs:['建议表达','依据与边界'],checks:['不替对方承诺','回填草稿后仍由本人发送']},
 'connect-2':{kind:'skill',trigger:'协作|群|会议|分工|共创',purpose:'整理多人协作的目标、分工和依赖',steps:['区分各方已明确的观点与未决事项','整理候选分工和依赖','标明需相关成员确认的承诺'],outputs:['共同目标与分歧','分工与依赖','待确认事项'],checks:['候选负责人不等于已接受','保留异议和未知']},
 'execute-0':{kind:'skill',trigger:'计划|步骤|排期|推进',purpose:'把目标整理成可确认、可验收的行动步骤',steps:['分解目标与前置条件','安排顺序、负责人和期限候选','给出每一步的完成证据'],outputs:['目标与边界','步骤与依赖','验收标准'],checks:['计划不等于执行完成','新增对外行动需单独授权']},
 'execute-1':{kind:'tool',trigger:'操作|发送|发布|部署|下单',purpose:'检查具体操作的输入、权限和执行条件',steps:['列出需要执行的动作和对象','核对已有授权与工具是否可用','仅依据真实回执报告结果；无工具时交付操作草稿'],outputs:['动作与对象','权限与工具','执行状态与回执'],checks:['缺少回执不声称已操作','模型不能扩大工具权限'],review:'required',limitations:'当前准备操作方案；邮件、浏览器操作、支付、部署等外部执行工具尚未接通。'},
 'execute-2':{kind:'monitor',trigger:'监督|监控|超时|重试|运行状态',purpose:'从运行记录中定位停滞、失败和待处理状态',steps:['核对最近状态、时间和真实回执','区分处理中、失败和结果未知','提出恢复办法，未知外部效果不自动重放'],outputs:['运行现状','异常与证据','恢复建议'],checks:['不依据模型猜测改写任务状态','恢复仍受累计预算限制'],limitations:'运行器负责本地任务的超时、暂停和重试限制；此能力分析所选记录，不额外创建常驻模型。'},
 'execute-3':{kind:'check',trigger:'验收|完成证据|交付核对',purpose:'核对成果是否满足已确认的验收条件',steps:['逐项列出验收标准','核对测试、文件或操作回执','给出通过、未通过、未知及缺少的证据'],outputs:['验收条件','证据核对','结论与缺口'],checks:['模型自述不等于完成证据','最终采纳由用户决定'],review:'required'},
};
export const DEFINITIONS=SYSTEMS.flatMap(system=>system.roles.map((name,index)=>{
 const id=`${system.id}-${index}`,spec=specs[id];
 return {id,system:system.id,name,version:2,status:'registered',instance_policy:'load_on_demand',...spec,
  input_schema:{type:'object',required:['goal'],properties:{goal:{type:'string'},source_refs:{type:'array',description:'仅本次明确选择且有权读取的资料'},constraints:{type:'string'}}},
  output_schema:{format:'markdown',sections:spec.outputs},tool_allowlist:['text.compose','context.read','document.read','search.local','web.search','web.read'],
  context_scope:'selected_sources_only',review_policy:spec.review||'conditional',limitations:spec.limitations||null,
 };
}));
