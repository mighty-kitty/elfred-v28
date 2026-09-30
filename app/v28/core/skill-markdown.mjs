/**
 * SKILL.md 解析：把一条能力卡的说明书拆成界面能直接用的几块。
 *
 * 为什么要有它：说明书是 markdown（`## 什么时候用 / ## Procedure / ## Inputs ...`），
 * 界面却只能拿整段文本去塞"它能替你做""使用说明""输入""输出"——压成一行就是乱码，
 * 输入输出永远是空的。解析放在共用的 core 里，前后端同一份规则，别在页面里各写一遍。
 *
 * 我们见过的两种真实写法（别只认一种）：
 *   · 手写中文：`## 什么时候用 / ## 怎么做 / ## 交付什么 / ## 注意`
 *   · Skill Foundry 生成：`## When to Use / ## Inputs / ## Procedure / ## Verification / ## Pitfalls`
 * 所以标题按中英关键词匹配；匹配不到的小节原样留在 sections 里，供"完整说明"直接渲染。
 *
 * 铁律：解析不出来就不编。宁可让界面退回渲染原文，也不许造"步骤一/步骤二"这种假内容。
 */

/** 各字段认的小节名（小写、去掉空格与标点后比较） */
const SECTIONS = {
  whenToUse: ['什么时候用', '适用场景', '使用场景', 'when to use', 'whentouse', 'when'],
  procedure: ['怎么做', '步骤', '工作步骤', '流程', 'procedure', 'steps', 'workflow', 'how'],
  inputs: ['输入', '需要的输入', '需要什么', '参数', '前置条件', 'inputs', 'input', 'preconditions', 'parameters'],
  outputs: ['交付什么', '交付', '输出', '产出', '结果', 'outputs', 'output', 'deliverables', 'deliverable'],
  limits: ['注意', '限制', '不能做什么', '边界', '不要用', 'do not use', 'pitfalls', 'limitations', 'safety and approval'],
  checks: ['验收', '验收标准', '检查', 'verification', 'checks', 'acceptance'],
};

/** 标题规范化：小写、去掉空白和标点，中文标题也走同一条路 */
const normalize = (text) => String(text ?? '')
  .toLowerCase()
  .replace(/[\s:：、,，.。/\\|_`*#-]/g, '');

function sectionKey(title) {
  const key = normalize(title);
  for (const [field, names] of Object.entries(SECTIONS)) {
    if (names.some((name) => key === normalize(name))) return field;
  }
  return null;
}

/** 极简 frontmatter：只认 `key: value` 这种单层键值，够用就好，不引 YAML 依赖 */
export function readFrontmatter(markdown) {
  const text = String(markdown ?? '');
  const match = text.match(/^\s*---\s*\n([\s\S]*?)\n\s*---\s*(?:\n|$)/);
  if (!match) return { data: {}, body: text };
  const data = {};
  for (const line of match[1].split('\n')) {
    const row = line.match(/^\s*([A-Za-z0-9_-]+)\s*:\s*(.*)$/);
    if (!row) continue;
    data[row[1]] = row[2].trim().replace(/^["']|["']$/g, '');
  }
  return { data, body: text.slice(match[0].length) };
}

/** 把一段正文拆成条目：有序列表、无序列表各算一条，普通段落按句算一条 */
function itemsOf(lines) {
  const items = [];
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    const ordered = line.match(/^\d+[.)、]\s*(.+)$/);
    const bullet = line.match(/^[-*+•]\s*(.+)$/);
    if (ordered || bullet) { items.push((ordered || bullet)[1].trim()); continue; }
    if (/^[#>|]/.test(line)) continue;
    for (const sentence of line.split(/(?<=[。；;!?！？])\s*/)) {
      const clean = sentence.trim();
      if (clean) items.push(clean);
    }
  }
  return items.filter(Boolean);
}

/** Foundry 的输入写法：`- \`documentTitle\` (string, required): 说明` → `documentTitle（必填）` */
function readableInput(item) {
  const row = String(item).match(/^`?([A-Za-z0-9_.-]+)`?\s*(?:\(([^)]*)\))?\s*[:：]?\s*(.*)$/);
  if (!row) return String(item);
  const [, name, meta = '', rest = ''] = row;
  if (!name || !rest) return String(item);
  const required = /required/i.test(meta) && !/optional/i.test(meta);
  const detail = rest.trim();
  return `${name}${required ? '（必填）' : ''}${detail ? `：${detail.slice(0, 60)}` : ''}`;
}

/**
 * 解析一份 SKILL.md。
 * @param {string} markdown
 * @returns {{
 *   title: string, description: string, summary: string,
 *   canDo: string[], steps: string[], inputs: string[], outputs: string[], limits: string[], checks: string[],
 *   sections: Array<{title: string, items: string[], field: string|null}>,
 * }}
 */
export function parseSkillMarkdown(markdown) {
  const { data, body } = readFrontmatter(markdown);
  const lines = body.split('\n');
  const sections = [];
  let current = null;
  let intro = [];

  for (const line of lines) {
    const heading = line.match(/^(#{1,3})\s+(.+?)\s*$/);
    if (heading) {
      const level = heading[1].length;
      const title = heading[2].trim();
      if (level === 1 && !current && sections.length === 0 && intro.length === 0) {
        // 一级标题就是这条 skill 的名字，不当小节
        continue;
      }
      current = { title, field: sectionKey(title), items: [] };
      sections.push(current);
      continue;
    }
    if (current) current.items.push(line);
    else intro.push(line);
  }

  const pick = (field) => sections.filter((section) => section.field === field).flatMap((section) => itemsOf(section.items));
  const description = String(data.description || '').trim()
    || String((intro.find((line) => line.trim()) || '')).trim();
  const whenToUse = pick('whenToUse');
  const inputs = pick('inputs').map(readableInput);
  const procedure = pick('procedure');

  return {
    title: String(data.name || '').trim(),
    description,
    // 卡面那一行小字：优先 frontmatter 的 description，其次"什么时候用"的第一句
    summary: description || whenToUse[0] || '',
    canDo: whenToUse,
    steps: procedure,
    inputs,
    outputs: pick('outputs'),
    limits: pick('limits'),
    checks: pick('checks'),
    sections: sections.map((section) => ({ title: section.title, field: section.field, items: itemsOf(section.items) })),
  };
}

/**
 * 卡面小字：一句话说清这张卡是干什么的。
 * 解析不到就返回空串，由调用方决定退回什么（不拿 markdown 原文压平来充数）。
 */
export function skillCardCopy(markdown, { limit = 60 } = {}) {
  const { summary } = parseSkillMarkdown(markdown);
  const text = summary.replace(/\s+/g, ' ').trim();
  if (!text) return '';
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}
