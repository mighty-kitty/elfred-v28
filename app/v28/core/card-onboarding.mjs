/**
 * 第一张能力卡的初始化：选项表 + 模板生成。前后端共用一份（做法与 `dimensions.mjs` 一致）——
 * 前端拿它画"选框"，服务端拿它把选项拼成真正能用的 skill（说明书 / 输入 / 步骤 / 任务草稿）。
 *
 * 三条硬规矩（都来自设计稿《设计-第一张能力卡初始化流程-v1.md》）：
 *   ① 选框是筛选器：选项直接决定生成哪张卡、卡里写什么；
 *   ② 说明书必须是 SKILL.md 的四小节（什么时候用 / 怎么做 / 交付什么 / 注意），
 *      这样卡片详情能直接渲染出"能做到什么 / 步骤 / 交付"，不用另做适配；
 *   ③ 初始化不承诺分数：这里只负责"生成一张起点卡"，等级与分数仍只由验收过的成果推。
 */

export const SYSTEM_LABELS = { explore: '探索', advise: '参谋', create: '创作', connect: '连接', execute: '执行' };
export const SYSTEMS = ['explore', 'advise', 'create', 'connect', 'execute'];

/**
 * 一次只做一张（2026-09-29 改）。
 * 原来最多 3 张：一次给出三张没成果的空卡，用户既挑不出哪张该先用，卡组也显得虚。
 * 第一次进来只要**一张能用的卡**就够 —— 剩下的等真用过、有验收结果了再"再来一张"。
 */
export const MAX_CARDS_PER_RUN = 1;
export const MAX_CUSTOM_TEXT = 200;

/**
 * 预置卡：一张卡 = 一个"我们早就知道怎么做"的做法。
 * 字段说明：
 *   id        稳定标识（生成后记在 skill 的 onboarding.preset_id 上，用于去重与统计）
 *   system    主责系统（决定卡片进哪一维）
 *   title     卡片标题
 *   canDo     一句话："它能替你做…"
 *   steps     说明书里的固定步骤（三条，够用且不啰嗦）
 *   inputs    这张卡要喂什么（写进 skill.parameters，"用它做一件事"时会问）
 *   deliver   交付什么（写进说明书，也是任务的验收标准）
 *   preStep   可选的前置步骤：交给**另一个**系统先做一件事（写进 skill.workflow）
 */
export const CARD_PRESETS = [
  // ── 探索 · 洞察 ────────────────────────────────────────────────
  {
    id: 'explore-sources', system: 'explore', title: '查资料并核实来源',
    canDo: '把零散资料查全，并按来源能不能核对分开标注。',
    steps: ['界定这次要查什么、哪些资料算数', '逐条查找并记下出处（标题与链接）', '把"已核实 / 待核实 / 互相矛盾"分成三列列出'],
    inputs: [{ name: '要查的问题', required: true, hint: '例如：2026 年国内大学生 AI 工具使用情况', default_value: '' }],
    deliver: '一份带出处的资料清单，外加一份"还没核实"的清单。',
  },
  {
    id: 'explore-watch', system: 'explore', title: '盯住一个主题的变化',
    canDo: '只报变化，不重复已经知道的事。',
    steps: ['确定主题和要盯的范围', '把当前状态记成基准', '之后每次只对比基准，列出新增与变化'],
    inputs: [
      { name: '要盯的主题', required: true, hint: '例如：某门课的作业提交规则', default_value: '' },
      { name: '多久看一次', required: false, hint: '不填就按每周', default_value: '每周' },
    ],
    deliver: '变化清单（只列变化的，没变化就明确说"没有变化"）。',
  },
  {
    id: 'explore-digest', system: 'explore', title: '把一堆资料整理成要点',
    canDo: '把长材料压成分类要点，并标出哪句来自哪里。',
    steps: ['通读并去掉重复内容', '按主题归类', '每类最多三条要点，关键结论标出来源'],
    inputs: [{ name: '要整理的内容', required: true, hint: '粘贴材料或选一份已保存的资料', default_value: '' }],
    deliver: '分类要点 + 未解决的疑问。',
  },
  // ── 参谋 · 判断 ────────────────────────────────────────────────
  {
    id: 'advise-compare', system: 'advise', title: '比较几个方案给建议',
    canDo: '用同一组标准比较方案，并说清什么情况下不该选它。',
    steps: ['列出候选方案，并把"什么都不做"也列进来', '用同一组标准逐项比较', '给出建议、适用条件和代价'],
    inputs: [
      { name: '要比较的方案', required: true, hint: '例如：三个实习 offer', default_value: '' },
      { name: '你最在意的标准', required: false, hint: '例如：成长空间 > 薪资', default_value: '' },
    ],
    deliver: '对比表 + 建议 + 不适用的情况。',
    preStep: { system: 'explore', goal: '收集这些方案的可核对信息（花费、条件、风险）' },
  },
  {
    id: 'advise-diagnose', system: 'advise', title: '拆解一个问题找原因',
    canDo: '把"为什么不行"拆成可以一条条验证的原因。',
    steps: ['重述问题，划清边界', '区分事实、假设和约束', '列出可能原因，并排出先验证哪一个'],
    inputs: [
      { name: '遇到的问题', required: true, hint: '例如：课程项目跑到一半就卡住', default_value: '' },
      { name: '已经试过的办法', required: false, hint: '', default_value: '' },
    ],
    deliver: '原因假设清单 + 下一步先验证什么。',
  },
  {
    id: 'advise-risk', system: 'advise', title: '检查一个方案的风险',
    canDo: '找出方案最可能失败的地方，并给出停止条件。',
    steps: ['列出方案依赖的假设', '按"影响 × 可能性"排序风险', '每条给出缓解办法与停止条件'],
    inputs: [{ name: '要检查的方案', required: true, hint: '把方案要点写进来', default_value: '' }],
    deliver: '风险清单 + 缓解办法 + 什么时候该停。',
  },
  // ── 创作 · 表达 ────────────────────────────────────────────────
  {
    id: 'create-draft', system: 'create', title: '写一份文档 / 文稿',
    canDo: '先搭结构再填内容，交一份能直接改的完整稿。',
    steps: ['确认读者、用途和边界', '先给结构，再逐段填内容', '完稿后标出需要你确认或补充的地方'],
    inputs: [
      { name: '要写什么', required: true, hint: '例如：一份课程项目报告', default_value: '' },
      { name: '给谁看', required: false, hint: '例如：老师 / 队友 / 甲方', default_value: '' },
    ],
    deliver: '可直接编辑的完整文稿 + 待确认项。',
    preStep: { system: 'explore', goal: '按主题收集可引用的资料与事实' },
  },
  {
    id: 'create-edit', system: 'create', title: '改一段文字（语气 / 结构）',
    canDo: '先说清现在的问题在哪，再给完整修订稿。',
    steps: ['指出原文的问题（结构 / 语气 / 冗余）', '给出修改后的完整版本', '列出改了哪几处、为什么'],
    inputs: [
      { name: '要改的文字', required: true, hint: '直接粘贴', default_value: '' },
      { name: '想要的效果', required: false, hint: '例如：更正式 / 更短 / 少用术语', default_value: '' },
    ],
    deliver: '修订稿 + 改动说明。',
  },
  {
    id: 'create-visual', system: 'create', title: '出一张图的制作说明',
    canDo: '把"想要一张什么图"写成能交给别人或工具执行的说明。',
    steps: ['确定尺寸、风格和信息层级', '写清画面元素与文案', '列出交付前要检查的项'],
    inputs: [{ name: '图的用途', required: true, hint: '例如：社团招新海报', default_value: '' }],
    deliver: '一份制作说明（含规格、元素、文案、检查项）。',
  },
  // ── 连接 · 链接 ────────────────────────────────────────────────
  {
    id: 'connect-script', system: 'connect', title: '准备一段沟通话术',
    canDo: '基于你要表达的核心和底线，给一段能直接改的话术。',
    steps: ['厘清你要表达的核心与不想答应的部分', '按对方的立场调整说法', '给出可编辑的草稿与注意事项'],
    inputs: [
      { name: '要跟谁说、为什么', required: true, hint: '例如：跟导师解释延期', default_value: '' },
      { name: '你的底线', required: false, hint: '例如：不接受通宵改稿', default_value: '' },
    ],
    deliver: '可编辑话术 + 注意事项（不替你发送）。',
  },
  {
    id: 'connect-actions', system: 'connect', title: '整理群聊里的行动项',
    canDo: '从聊天里挑出真正要做的事，并标上负责人和出处。',
    steps: ['只读群内可见的内容', '分出"已说定"和"还没确认"', '每条行动项标负责人，并附上原话那句'],
    inputs: [{ name: '要整理的聊天记录', required: true, hint: '粘贴记录，或选择已授权的会话', default_value: '' }],
    deliver: '行动项表 + 待确认清单。',
  },
  {
    id: 'connect-match', system: 'connect', title: '找合适的候选人 / 资源',
    canDo: '按你给的条件逐条核对，并说清哪条没证据。',
    steps: ['把需求写成必要条件', '对每份候选资料逐条核对', '给出匹配理由与未知项'],
    inputs: [
      { name: '要找什么样的人 / 资源', required: true, hint: '例如：会剪视频的队友', default_value: '' },
      { name: '候选名单', required: false, hint: '没有就写"手头没有名单"', default_value: '' },
    ],
    deliver: '候选与依据 + 待核实项。',
  },
  // ── 执行 · 交付 ────────────────────────────────────────────────
  {
    id: 'execute-steps', system: 'execute', title: '把目标拆成可执行步骤',
    canDo: '把"想做成的事"拆成每步都有完成证据的步骤。',
    steps: ['把目标拆成有完成证据的步骤', '安排顺序与前置条件', '标出每一步的验收标准'],
    inputs: [
      { name: '要完成的目标', required: true, hint: '例如：两周内做完课程设计', default_value: '' },
      { name: '时间或资源限制', required: false, hint: '', default_value: '' },
    ],
    deliver: '步骤表（含前置、验收标准）。',
  },
  {
    id: 'execute-schedule', system: 'execute', title: '安排一次日程 / 排期',
    canDo: '排出先后与依赖，并留出缓冲。',
    steps: ['列出要做的事和各自需要的时间', '排出先后与依赖关系', '标出风险点和缓冲时间'],
    inputs: [
      { name: '要安排的事', required: true, hint: '例如：结课前的三件交付', default_value: '' },
      { name: '时间范围', required: false, hint: '例如：下两周', default_value: '' },
    ],
    deliver: '排期表 + 风险与缓冲。',
  },
  {
    id: 'execute-check', system: 'execute', title: '核对交付物是否达标',
    canDo: '逐条对照标准核对，通过、不通过、未知分开写。',
    steps: ['列出这次的验收标准', '逐项核对并标出证据', '给出通过 / 未通过 / 未知，以及缺口'],
    inputs: [
      { name: '要核对的东西', required: true, hint: '粘贴交付物或选择文件', default_value: '' },
      { name: '验收标准', required: false, hint: '不填就按通用标准核对', default_value: '' },
    ],
    deliver: '核对表 + 缺口清单。',
  },
];

/** 第二屏的四组偏好；每组都有默认值，所以"不看也能过" */
export const PREFERENCE_GROUPS = [
  {
    id: 'conclusion', label: '先给什么', defaultValue: 'conclusion-first',
    options: [
      { value: 'conclusion-first', label: '先给结论', note: '结论在前，依据随后' },
      { value: 'process-first', label: '先给过程', note: '先交代过程和依据，最后给结论' },
    ],
  },
  {
    id: 'length', label: '篇幅', defaultValue: 'short',
    options: [
      { value: 'short', label: '简短', note: '能一行说清就不写三行' },
      { value: 'detailed', label: '详细', note: '依据、取舍都写出来' },
    ],
  },
  {
    id: 'sources', label: '来源', defaultValue: 'cite',
    options: [
      { value: 'cite', label: '必须引用来源', note: '没来源的写"未知"，不猜' },
      { value: 'free', label: '可以不引', note: '仍不许编造事实' },
    ],
  },
  {
    id: 'review', label: '复核', defaultValue: 'auto',
    options: [
      { value: 'auto', label: '按任务自动判断', note: '需要时才会加复核' },
      { value: 'independent', label: '要独立复核', note: '成果先过一遍独立核对' },
    ],
  },
];

/* ── 分支选择树（2026-09-29 改）──────────────────────────────────────────────
 *
 * 为什么改：原来是"第一屏 15 张卡 + 第二屏四组固定偏好"，三段之间没有因果——
 * 无论选哪张卡，第二屏都是同样四组题，读起来像填表（真机反馈：选起来很吃力）。
 *
 * 现在：每页 3 个选项，选项决定下一题；路径上的每个选项除了指向某张卡，
 * 还携带若干**内容片段**，最后由「骨架（卡）+ 片段（路径）」拼出这张卡的说明书。
 * 所以**同一张卡走不同路径，就是两份不同的 skill**：骨架给固定的三条步骤与默认交付，
 * 片段改"注意""交付"、加输入、也能替换某一步。
 *
 * 三条规矩：
 *   ① 每页最多 3 个选项，且必须是用户自己的话（不出现系统名）；
 *   ② 每题都能走"都不太对，我自己说一句"（自由文本 → 按关键词落到某张卡）；
 *   ③ 片段带 group 的，同组后选覆盖先选（不会出现"只用我给的材料"和"允许联网"同时写进说明书）。
 */

/**
 * 内容片段。字段：
 *   group          互斥组（同组只保留最后一次选择）
 *   notes          追加到说明书"注意"里的句子
 *   deliver        替换这张卡默认的"交付什么"
 *   deliverAppend  追加到"交付什么"后面
 *   inputs         追加输入项（写进 skill.parameters）
 *   step           { index, text } 替换第 index 条步骤（从 1 数）
 */
export const CARD_FRAGMENTS = [
  // 资料从哪来
  { id: 'scope-given', group: 'scope', notes: ['只在本人提供的材料里查；材料不够就写"未知"，不联网补充'] },
  { id: 'scope-web', group: 'scope', notes: ['允许联网检索公开来源；只引用能公开核对的出处，没出处的一律标"未知"'] },
  { id: 'scope-both', group: 'scope', notes: ['先查本人给的材料，不够时再联网补；两类来源分开标注'] },
  // 盯变化的频率
  { id: 'cadence-daily', group: 'cadence', notes: ['每天看一次；没有变化就明确说"没有变化"，不要凑内容'] },
  { id: 'cadence-weekly', group: 'cadence', notes: ['每周看一次；只报与上次基准相比的新增与变化'] },
  { id: 'cadence-smart', group: 'cadence', notes: ['频率由你判断，只在真有变化时提醒我'] },
  // 给谁看（交付形态与语气）
  {
    id: 'aud-formal', group: 'audience',
    notes: ['读者是老师/上级：语气正式、结论在前、关键判断标出处'],
    deliverAppend: '另附一页给人看的要点摘要（正式、结论在前）',
  },
  {
    id: 'aud-peer', group: 'audience',
    notes: ['读者是队友/同事：先说结论、少客套，留出别人直接改的余地'],
    deliverAppend: '另附一段可以直接转给队友的结论',
  },
  {
    id: 'aud-self', group: 'audience',
    notes: ['只给自己看：结构和要点清楚就行，措辞不用打磨'],
    deliverAppend: '不用额外摘要，自己能看懂就行',
  },
  // 拆步骤、排期
  { id: 'step-evidence', group: 'step-mode', notes: ['每一步都要有可核对的完成证据；没有证据的不算完成'] },
  { id: 'step-loose', group: 'step-mode', notes: ['先给大致步骤和顺序就行，不用写验收标准'] },
  { id: 'step-deps', group: 'step-mode', notes: ['标出步骤之间的先后依赖与前置条件', '哪一步卡住要指出它前面缺什么'] },
  { id: 'schedule-fixed', group: 'schedule-mode', notes: ['有固定截止时间：倒排到最后一步，并标出最晚该从哪天开始'] },
  { id: 'schedule-loose', group: 'schedule-mode', notes: ['不排死：给节奏建议和大致先后就行'] },
  { id: 'schedule-buffer', group: 'schedule-mode', notes: ['每段之间留出缓冲，并指出最可能被拖延的一步'] },
  // 改文字
  { id: 'edit-formal', group: 'edit-goal', notes: ['改得更正式、更稳妥；术语保留但要说清'] },
  { id: 'edit-short', group: 'edit-goal', notes: ['改短：先砍重复和铺垫，再说改了什么'] },
  { id: 'edit-plain', group: 'edit-goal', notes: ['改得更通俗：少术语、短句、能念出来'] },
  // 整理材料
  { id: 'digest-notes', group: 'digest-kind', notes: ['按主题归类，每类最多三条，关键结论标出来源'] },
  { id: 'digest-facts', group: 'digest-kind', notes: ['只摘事实与数字，不做解读、也不要给建议'] },
  // 具体做法上的固定补充
  { id: 'compare-exclusions', notes: ['除了建议本身，要写清"什么情况下不该选它"'] },
  { id: 'script-bottom-line', notes: ['把我不想答应的部分写清楚，并给两套说法（强硬 / 缓和）'] },
  { id: 'actions-owner', notes: ['每条行动项都要写负责人，并附上原话那一句'] },
  { id: 'match-evidence', notes: ['每条匹配理由都要能指回一份材料；没依据的写"未知"'] },
];

const fragmentById = (id) => CARD_FRAGMENTS.find((item) => item.id === id) || null;

/**
 * 题目树。每个 option：
 *   id / label / note   界面上三个选项就来自这里
 *   next                下一题（没有就是最后一题）
 *   preset              这个选项把卡定成哪一张（路径上最后一个声明 preset 的选项说话）
 *   fragments           这个选项往说明书里写什么
 */
export const CARD_QUESTIONS = {
  root: {
    id: 'root',
    title: '你现在最想让它帮你做什么？',
    options: [
      { id: 'r1-clarify', label: '有一件事我想搞清楚', next: 'clarify' },
      { id: 'r1-make', label: '有一份东西我想做出来', next: 'make' },
      { id: 'r1-push', label: '有件事正在发生，我想推进或收尾', next: 'push' },
    ],
  },
  clarify: {
    id: 'clarify',
    title: '这件事更像哪一种？',
    options: [
      { id: 'r2-clarify-sources', label: '把资料查全，按来源能不能核对分开写', preset: 'explore-sources', next: 'sourcesScope' },
      { id: 'r2-clarify-watch', label: '盯住一个主题的变化，只报新增', preset: 'explore-watch', next: 'watchCadence' },
      { id: 'r2-clarify-judge', label: '我拿不准，想要个判断', next: 'judgeKind' },
    ],
  },
  sourcesScope: {
    id: 'sourcesScope',
    title: '资料从哪来？',
    options: [
      { id: 'r3-scope-given', label: '只用我给你的材料', fragments: ['scope-given'], next: 'audience' },
      { id: 'r3-scope-web', label: '允许上网找公开来源', fragments: ['scope-web'], next: 'audience' },
      { id: 'r3-scope-both', label: '两者都行', fragments: ['scope-both'], next: 'audience' },
    ],
  },
  watchCadence: {
    id: 'watchCadence',
    title: '多久看一次？',
    options: [
      { id: 'r3-watch-daily', label: '每天看一次', fragments: ['cadence-daily'] },
      { id: 'r3-watch-weekly', label: '每周看一次', fragments: ['cadence-weekly'] },
      { id: 'r3-watch-smart', label: '你判断，有变化再告诉我', fragments: ['cadence-smart'] },
    ],
  },
  judgeKind: {
    id: 'judgeKind',
    title: '你想让判断落在哪一件事上？',
    options: [
      { id: 'r3-judge-diagnose', label: '把原因一条条拆出来', preset: 'advise-diagnose' },
      { id: 'r3-judge-risk', label: '找出最可能失败的地方', preset: 'advise-risk' },
      { id: 'r3-judge-compare', label: '把几个方案摆一起比，给建议', preset: 'advise-compare', fragments: ['compare-exclusions'] },
    ],
  },
  make: {
    id: 'make',
    title: '要做出来的是什么？',
    options: [
      { id: 'r2-make-draft', label: '从零写一份文稿', preset: 'create-draft', next: 'audience' },
      { id: 'r2-make-edit', label: '把现有的东西改顺、改清楚', next: 'editGoal', preset: 'create-edit' },
      { id: 'r2-make-digest', label: '把一堆零散材料整理成能用的', next: 'digestKind' },
    ],
  },
  audience: {
    id: 'audience',
    title: '这份东西主要给谁看？',
    options: [
      { id: 'r4-aud-formal', label: '老师 / 上级', fragments: ['aud-formal'] },
      { id: 'r4-aud-peer', label: '队友 / 同事', fragments: ['aud-peer'] },
      { id: 'r4-aud-self', label: '只有我自己', fragments: ['aud-self'] },
    ],
  },
  editGoal: {
    id: 'editGoal',
    title: '你想往哪个方向改？',
    options: [
      { id: 'r3-edit-formal', label: '更正式一点', fragments: ['edit-formal'] },
      { id: 'r3-edit-short', label: '短一点，去掉冗余', fragments: ['edit-short'] },
      { id: 'r3-edit-plain', label: '更通俗，少用术语', fragments: ['edit-plain'] },
    ],
  },
  digestKind: {
    id: 'digestKind',
    title: '整理成什么形态？',
    options: [
      { id: 'r3-digest-notes', label: '分类要点，标出来源', preset: 'explore-digest', fragments: ['digest-notes'] },
      { id: 'r3-digest-facts', label: '只摘事实与数字，不要解读', preset: 'explore-digest', fragments: ['digest-facts'] },
      { id: 'r3-digest-visual', label: '一张图 / 海报的制作说明', preset: 'create-visual' },
    ],
  },
  push: {
    id: 'push',
    title: '这一步最要紧的是什么？',
    options: [
      { id: 'r2-push-steps', label: '拆成能一步步做的步骤', preset: 'execute-steps', next: 'stepMode' },
      { id: 'r2-push-schedule', label: '排时间、排先后', preset: 'execute-schedule', next: 'scheduleMode' },
      { id: 'r2-push-people', label: '跟人有关：要说话、群里的行动项、找人', next: 'peopleKind' },
    ],
  },
  stepMode: {
    id: 'stepMode',
    title: '步骤要多严？',
    options: [
      { id: 'r3-step-evidence', label: '每步都要有完成证据', fragments: ['step-evidence'] },
      { id: 'r3-step-loose', label: '先给大致步骤就行', fragments: ['step-loose'] },
      { id: 'r3-step-deps', label: '重点是先后依赖', fragments: ['step-deps'] },
    ],
  },
  scheduleMode: {
    id: 'scheduleMode',
    title: '时间怎么定？',
    options: [
      { id: 'r3-schedule-fixed', label: '有固定截止日', fragments: ['schedule-fixed'] },
      { id: 'r3-schedule-loose', label: '我自己定节奏', fragments: ['schedule-loose'] },
      { id: 'r3-schedule-buffer', label: '怕临时有事，要留缓冲', fragments: ['schedule-buffer'] },
    ],
  },
  peopleKind: {
    id: 'peopleKind',
    title: '跟人有关的哪一种？',
    options: [
      { id: 'r3-people-script', label: '要跟某个人说一件事', preset: 'connect-script', fragments: ['script-bottom-line'] },
      { id: 'r3-people-actions', label: '从群聊里挑出要做的事', preset: 'connect-actions', fragments: ['actions-owner'] },
      { id: 'r3-people-match', label: '找合适的人或资源', preset: 'connect-match', fragments: ['match-evidence'] },
    ],
  },
};

export const questionById = (id) => CARD_QUESTIONS[id] || null;

/**
 * 把一条路径（选项 id，按答题顺序）解成"哪张卡 + 哪些片段"。
 * 路径必须从 root 开始、一路走到没有 next 的选项；中途不认识或没答完都会如实报错。
 */
export function resolvePath(ids = []) {
  const picked = Array.isArray(ids) ? ids.map((item) => String(item)) : [];
  const trail = [];
  let node = CARD_QUESTIONS.root;
  let presetId = null;
  const fragmentIds = [];
  for (const id of picked) {
    const option = node?.options.find((item) => item.id === id);
    if (!option) return { ok: false, reason: `路径里有不认识的选项：${id}`, trail, preset: null, fragments: [] };
    trail.push({ question: node.title, id: option.id, label: option.label });
    if (option.preset) presetId = option.preset;
    for (const fragment of option.fragments || []) fragmentIds.push(fragment);
    node = option.next ? questionById(option.next) : null;
    if (!node) break;
  }
  if (node) return { ok: false, reason: '还有没答完的问题', trail, preset: null, fragments: [] };
  if (!presetId) return { ok: false, reason: '这条路径没有落到任何一张卡上', trail, preset: null, fragments: [] };
  const preset = presetById(presetId);
  if (!preset) return { ok: false, reason: `路径指向的卡不存在：${presetId}`, trail, preset: null, fragments: [] };
  return { ok: true, preset, fragments: resolveFragments(fragmentIds), fragmentIds, trail };
}

/** 片段去重 + 同组后选覆盖先选 */
export function resolveFragments(items = []) {
  const seen = new Map();
  const order = [];
  for (const raw of Array.isArray(items) ? items : []) {
    // 常见是片段 id；也允许直接给一条临时片段（比如"本人原话：…"这种只属于这次生成的）
    const fragment = typeof raw === 'string'
      ? fragmentById(raw)
      : (raw && typeof raw === 'object' ? (fragmentById(String(raw.id)) || raw) : null);
    if (!fragment || !fragment.id) continue;
    const key = fragment.group || fragment.id;
    if (!seen.has(key)) order.push(key);
    seen.set(key, fragment);
  }
  return order.map((key) => seen.get(key));
}

/** 用户自己写一句话那条路：先按关键词落到某张现成卡，判不出再造一张"其它"卡 */
const TEXT_PRESET_RULES = [
  { pattern: /核对|达标|验收|检查.*(交付|成果)|有没有做完/, id: 'execute-check' },
  { pattern: /排期|日程|时间表|安排.*时间|倒排|什么时候做/, id: 'execute-schedule' },
  { pattern: /拆|步骤|计划|路线|怎么推进/, id: 'execute-steps' },
  { pattern: /话术|怎么跟|怎么说|说服|解释|沟通/, id: 'connect-script' },
  { pattern: /群聊|群消息|聊天记录|行动项/, id: 'connect-actions' },
  { pattern: /找人|候选人|队友|资源|招/, id: 'connect-match' },
  { pattern: /海报|图片|封面|配图|图/, id: 'create-visual' },
  { pattern: /改|润色|精简|语气|通顺/, id: 'create-edit' },
  { pattern: /写|文稿|报告|文案|稿|说明/, id: 'create-draft' },
  { pattern: /查资料|检索|找资料|调研|来源|核实/, id: 'explore-sources' },
  { pattern: /盯|变化|更新|跟进|动态/, id: 'explore-watch' },
  { pattern: /整理|要点|摘要|归纳|提炼/, id: 'explore-digest' },
  { pattern: /比较|选哪|哪个更好|方案/, id: 'advise-compare' },
  { pattern: /风险|失败|踩坑/, id: 'advise-risk' },
  { pattern: /原因|为什么.*(不行|卡)|卡住|搞不懂/, id: 'advise-diagnose' },
];

export function presetIdFromText(text) {
  const value = String(text || '');
  for (const rule of TEXT_PRESET_RULES) if (rule.pattern.test(value)) return rule.id;
  return null;
}

export const presetById = (id) => CARD_PRESETS.find((item) => item.id === id) || null;

const PREFERENCE_SENTENCES = {
  conclusion: {
    'conclusion-first': '先给结论，再补依据',
    'process-first': '先交代过程和依据，最后给结论',
  },
  length: { short: '输出保持简短，能一行说清就不写三行', detailed: '输出可以详细，把依据和取舍都写出来' },
  sources: { cite: '涉及事实必须标明来源，没有来源就写"未知"，不猜', free: '不强制标来源，但同样不许编造事实' },
  review: { independent: '成果先经过一次独立复核再给你', auto: '复核按任务情况自动决定，需要时才会加' },
};

/** 把用户的选择补成完整偏好（没选就用默认值） */
export function normalizePreferences(input = {}) {
  const out = {};
  for (const group of PREFERENCE_GROUPS) {
    const value = group.options.some((option) => option.value === input?.[group.id]) ? input[group.id] : group.defaultValue;
    out[group.id] = value;
  }
  return out;
}

/**
 * 偏好翻译成人话约束（写进说明书"注意"，也是任务约束）。
 * 默认只写**改成非默认值**的那几条：默认值不是用户表达的偏好，全写进去就是噪音
 * （一手卡片的"注意"里挂着四条谁都没选过的套话，看着像填充）。
 */
export function preferenceNotes(preferences = {}, { onlyChanged = true } = {}) {
  const prefs = normalizePreferences(preferences);
  return PREFERENCE_GROUPS
    .filter((group) => !onlyChanged || prefs[group.id] !== group.defaultValue)
    .map((group) => PREFERENCE_SENTENCES[group.id][prefs[group.id]]);
}

/**
 * 用自由文本造一张"其它"卡：系统按关键词粗判（判不出归执行），
 * 用户在第二屏可以改这个归属（界面上给一个五选一的小选择器）。
 */
export function inferSystem(text) {
  const value = String(text || '');
  if (/查|找资料|搜索|检索|核实|调研|整理资料/.test(value)) return 'explore';
  if (/比较|评估|分析|判断|建议|权衡|风险|原因/.test(value)) return 'advise';
  if (/写|改|润色|文案|稿|排版|图|海报|视频/.test(value)) return 'create';
  if (/沟通|话术|联系|邀请|群|协作|找人|匹配/.test(value)) return 'connect';
  return 'execute';
}

export function customPreset(text, system = null) {
  const clean = String(text || '').trim().slice(0, MAX_CUSTOM_TEXT);
  const title = clean.slice(0, 20) || '我自己描述的一件事';
  return {
    id: 'custom', system: SYSTEMS.includes(system) ? system : inferSystem(clean), title,
    canDo: clean || '按你描述的事做一次，然后沉淀成能力。',
    steps: ['把你说的这件事读一遍，确认这次要交付什么', '按你的偏好先起草一版', '标出需要你确认或补充的地方'],
    inputs: [{ name: '这次要处理的内容', required: true, hint: '把那件事的具体材料或背景贴在这里', default_value: '' }],
    deliver: '一版可编辑的成果，外加需要你确认的部分。',
    custom: true,
  };
}

/**
 * 校验一次初始化的选择。前端拿它做按钮可用性，服务端拿它挡非法输入。
 * @returns {{ok: boolean, reason?: string, presets: object[], customText: string, customSystem: string|null}}
 */
export function validateSelection(input = {}) {
  const ids = Array.isArray(input.preset_ids) ? [...new Set(input.preset_ids.map((item) => String(item)))] : [];
  const customText = String(input.custom_text || '').trim();
  const presets = [];
  for (const id of ids) {
    const preset = presetById(id);
    if (!preset) return { ok: false, reason: `未知的选项：${id}`, presets: [], customText, customSystem: null };
    presets.push(preset);
  }
  const customSystem = SYSTEMS.includes(input.custom_system) ? input.custom_system : null;
  if (customText) {
    if (customText.length > MAX_CUSTOM_TEXT) return { ok: false, reason: `"其它"最多 ${MAX_CUSTOM_TEXT} 字`, presets: [], customText, customSystem };
    presets.push(customPreset(customText, customSystem));
  }
  if (presets.length === 0) return { ok: false, reason: '先选一张现成的，或者写一句你想让它做的事', presets: [], customText, customSystem };
  if (presets.length > MAX_CARDS_PER_RUN) return { ok: false, reason: '一次只做一张卡：现成的和"其它"二选一', presets: [], customText, customSystem };
  return { ok: true, presets, customText, customSystem };
}

/**
 * 片段统一成对象（调用方给 id 或对象都行），再按互斥组去冲突。
 * 交给 `resolveFragments` 处理：它既认表里的 id，也认"只属于这次生成"的临时片段。
 */
const normalizeFragments = (fragments = []) => resolveFragments(Array.isArray(fragments) ? fragments : []);

/**
 * 说明书：四小节固定写法（卡片详情直接按这四节渲染）。
 * 内容 = 骨架（这张卡固定的三条步骤与默认交付）+ 路径上的片段；
 * 所以**同一张卡走不同路径，出来的说明书是不同的**。
 */
export function composeSkillMarkdown(preset, { fragments = [], preferences = {} } = {}) {
  const resolved = normalizeFragments(fragments);
  const notes = [...resolved.flatMap((fragment) => fragment.notes || []), ...preferenceNotes(preferences)];
  const replaced = new Map(resolved.filter((fragment) => fragment.step).map((fragment) => [fragment.step.index, fragment.step.text]));
  const steps = preset.steps.map((step, index) => `${index + 1}. ${replaced.get(index + 1) || step}`).join('\n');
  const override = resolved.map((fragment) => fragment.deliver).filter(Boolean).pop();
  const base = String(override || preset.deliver).trim().replace(/。$/, '');
  const extras = resolved.map((fragment) => fragment.deliverAppend).filter(Boolean);
  const deliver = `${[base, ...extras].join('；')}。`;
  return [
    '## 什么时候用',
    preset.canDo,
    '',
    '## 怎么做',
    steps,
    '',
    '## 交付什么',
    deliver,
    '',
    '## 注意',
    ...notes.map((note) => `- ${note}`),
    '- 只在已授权的资料范围内做；资料不够时写"未知"，不猜也不编',
    '',
  ].join('\n');
}

/** 这张卡要喂什么（写进 skill.parameters，"用它做一件事"时会问）；路径片段还能再加一项 */
export function composeToolParameters(preset, { fragments = [] } = {}) {
  const extra = normalizeFragments(fragments).flatMap((fragment) => fragment.inputs || []);
  return [...(preset.inputs || []), ...extra].map((item) => ({
    name: String(item.name).slice(0, 60),
    required: item.required === true,
    hint: String(item.hint || '').slice(0, 300),
    default_value: String(item.default_value || '').slice(0, 1000),
  }));
}

/** 前置步骤（写进 skill.workflow）：只有需要别的系统先干一件事时才给 */
export function composeToolWorkflow(preset) {
  if (!preset.preStep) return [];
  return [{ id: 'prep', system: preset.preStep.system, goal: preset.preStep.goal, depends: [] }];
}

/** 生成后立刻配一条任务草稿：目标＝这张卡 + 用户那句话，验收标准＝交付什么，约束＝路径片段 + 偏好 */
export function composeTaskDraft(preset, { fragments = [], preferences = {} } = {}) {
  const resolved = normalizeFragments(fragments);
  const goal = preset.custom
    ? String(preset.canDo || '').slice(0, 300)
    : `${preset.title}：${preset.canDo}`;
  return {
    goal,
    criteria: resolved.map((fragment) => fragment.deliver).filter(Boolean).pop() || preset.deliver,
    constraints: [...resolved.flatMap((fragment) => fragment.notes || []), ...preferenceNotes(preferences)].join('；'),
  };
}
