// 提交清单自检：这份副本里"该提交什么"逐条列出来，并验证关键文件真的在。
// 用途：提 PR / 交给同事之前跑一次，避免再出现"只交了调用方、没交上游源码"。
import { existsSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const normalize = (p) => p.replace(/\\/g, '/');
const count = (rel) => {
  const target = path.join(ROOT, rel);
  if (!existsSync(target)) return null;
  if (!statSync(target).isDirectory()) return 1;
  let files = 0;
  (function walk(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (['node_modules', '.venv', '__pycache__', '.next', '.git', 'data', 'logs'].includes(entry.name)) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else files += 1;
    }
  })(target);
  return files;
};

/** 提交时该带的路径（前缀即可，会递归统计） */
const MANIFEST = [
  ['app/v28/features/pages24', '第二/四页前端模块'],
  ['app/v28/core/dimensions.mjs', '题库 / 计分 / 五维估计（前后端共用）'],
  ['app/v28/core/capability-score.mjs', '能力分 / 卡片等级（前后端共用）'],
  ['app/v28/core/skill-markdown.mjs', 'SKILL.md 解析（卡片说明书）'],
  ['app/v28/core/card-onboarding.mjs', '第一张能力卡的选项表与模板（前后端共用）'],
  ['app/v28/core/agent-alignment.mjs', '领域对齐与理解度文案'],
  ['app/v28/core/memory-policy.mjs', '记忆分组与系统名'],
  ['app/v28/core/screen.ts', '路由类型'],
  ['app/v28/core/display-labels.ts', '显示文案规则'],
  ['app/v28/core/page2-identity.tsx', '把会话快照推进模块的挂件'],
  ['app/v28/features/live/types.ts', '快照 / 实体类型'],
  ['server/elfred/questionnaire', '后端：轻量测试模块'],
  ['server/elfred/profile-stats', '后端：主页聚合模块（三个数 + 勋章）'],
  ['server/elfred/skill-forge', '后端：能力生成模块（Skill Foundry）'],
  ['server/elfred/pa-gateway', '后端：规划网关模块（多步骤任务的方案）'],
  ['server/elfred/jev-verdict', '后端：Jev 判定模块（自动学到的理解的核对）'],
  ['server/elfred/card-onboarding', '后端：能力卡初始化模块（选框 → 真能用的 skill + 任务草稿）'],
  ['server/elfred/dependency-health.mjs', '后端：上游状态（探活 + 有没有用上）'],
  ['server/elfred/upstream.mjs', '后端：上游公共零件（地址白名单 + 带超时/上限的 JSON 调用）'],
  ['server/elfred/service.mjs', '宿主接缝：命令注册'],
  ['server/elfred/http.mjs', '宿主接缝：路由'],
  ['server/elfred/store.mjs', '宿主接缝：对象库'],
  ['server/elfred/runtime.mjs', '宿主接缝：任务运行时（我们改了：网关登记 / 方案采纳 / 各上游 tick）'],
  ['server/elfred/memory-hub.mjs', '记忆同步通道（我们改了：改用公共上游零件）'],
  ['server/elfred/memory-learning.mjs', '记忆学习（我们改了：自动学到的理解登记 Jev 核对）'],
  ['services', '三个上游模块源码（EMOS / Skill Foundry / PA 网关）'],
  ['tools/page2-checks', '探针（实机检查：第二/四页真机跑一遍）'],
  ['scripts', '副本自检脚本（check-extract / check-submit）'],
  ['tests/elfred/questionnaire.test.mjs', '测试：问卷'],
  ['tests/elfred/dependency-health.test.mjs', '测试：上游状态'],
  ['tests/elfred/memory-hub-sync.test.mjs', '测试：EMOS 记忆同步'],
  ['tests/elfred/skill-forge.test.mjs', '测试：能力生成'],
  ['tests/elfred/pa-gateway.test.mjs', '测试：规划网关'],
  ['tests/elfred/jev-verdict.test.mjs', '测试：Jev 判定'],
  ['tests/elfred/pages24-scoring.test.mjs', '测试：理解度 / 能力分 / SKILL.md 解析'],
  ['tests/elfred/pages24-projection.test.mjs', '测试：第二/四页投影（快照 → 视图）'],
  ['tests/elfred/upstream.test.mjs', '测试：上游公共零件'],
  ['tests/elfred/card-onboarding.test.mjs', '测试：能力卡初始化（含"生成的卡真能用"）'],
  ['docs/第二页第四页-资产清单与数据契约.md', '文档：资产与数据契约'],
  ['docs/第二页第四页-上游接线状态.md', '文档：上游接线状态与计划'],
];

/** 上游模块必须有的入口（少一个就说明源码没带全） */
const REQUIRED = [
  'services/README.md',
  'services/emos-memory/src/memory_system/api/elfred_bridge.py',
  'services/emos-memory/src/memory_system/api/server.py',
  'services/emos-memory/requirements.txt',
  'services/skill-foundry/adapter/__main__.py',
  'services/skill-foundry/adapter/api.py',
  'services/skill-foundry/pyproject.toml',
  'services/skill-foundry/uv.lock',
  'services/pa-gateway/app/main.py',
  'services/pa-gateway/pyproject.toml',
];

let failures = 0;
console.log('提交清单：');
for (const [rel, label] of MANIFEST) {
  const files = count(rel);
  if (files === null) { console.log(`  ✗ 缺：${rel}（${label}）`); failures += 1; }
  else console.log(`  ✓ ${normalize(rel).padEnd(46)} ${String(files).padStart(4)} 个文件   ${label}`);
}
console.log('\n上游模块入口：');
for (const rel of REQUIRED) {
  const ok = existsSync(path.join(ROOT, rel));
  if (!ok) failures += 1;
  console.log(`  ${ok ? '✓' : '✗'} ${rel}`);
}
console.log(failures === 0 ? '\n✓ 提交清单完整（上游源码在副本里）' : `\n✗ 有 ${failures} 项缺失，不要就这么提交`);
process.exit(failures === 0 ? 0 : 1);
