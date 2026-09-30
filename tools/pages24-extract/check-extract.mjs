// 第二/四页定向工作副本的自检：
//   1) 模块内的相对 import 能不能在副本里解析；解析不到的必须落在"宿主提供"清单里；
//   2) 后端 .mjs 语法检查；3) 关键资产在不在。
import { readdirSync, statSync, readFileSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const MODULE = path.join(ROOT, 'app/v28/features/pages24');

/** 宿主提供的依赖（没复制进来，运行时由主库给） */
const HOST = [
  'app/v27-7-state',
  'app/v28/core/runtime-context',
  'app/v28/core/runtime-panels',
  'app/v28/core/markdown-content',
  'app/v28/legacy/legacy-ui',
  'app/v28/features/home/memory-governance',
];

const normalize = (p) => p.replace(/\\/g, '/');
const walk = (dir) => {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
};
const resolveImport = (fromFile, spec) => {
  const base = path.resolve(path.dirname(fromFile), spec);
  return [base, `${base}.ts`, `${base}.tsx`, `${base}.mjs`, `${base}.js`, path.join(base, 'index.ts'), path.join(base, 'index.tsx'), path.join(base, 'index.mjs')]
    .some((candidate) => existsSync(candidate) && statSync(candidate).isFile());
};

let failures = 0;
const hostHits = new Set();
for (const file of walk(MODULE)) {
  if (!/\.(ts|tsx)$/.test(file)) continue;
  const text = readFileSync(file, 'utf8');
  for (const match of text.matchAll(/from\s+["'](\.[^"']+)["']/g)) {
    const spec = match[1];
    if (resolveImport(file, spec)) continue;
    const relTarget = normalize(path.relative(ROOT, path.resolve(path.dirname(file), spec))).replace(/\.(ts|tsx|mjs|js)$/, '');
    const host = HOST.some((prefix) => relTarget === prefix || relTarget.startsWith(prefix + '/'));
    if (host) hostHits.add(relTarget);
    else { console.log('✗ 引用解析不到：', normalize(path.relative(ROOT, file)), '→', spec); failures += 1; }
  }
}

const mjs = [
  'server/elfred/questionnaire/index.mjs',
  'server/elfred/profile-stats/index.mjs',
  'server/elfred/profile-stats/social.mjs',
  'server/elfred/profile-stats/badges.mjs',
  'server/elfred/skill-forge/index.mjs',
  'server/elfred/pa-gateway/index.mjs',
  'server/elfred/jev-verdict/index.mjs',
  'server/elfred/card-onboarding/index.mjs',
  'server/elfred/dependency-health.mjs',
  'server/elfred/upstream.mjs',
  'server/elfred/service.mjs',
  'server/elfred/http.mjs',
  'server/elfred/store.mjs',
  'app/v28/core/dimensions.mjs',
  'app/v28/core/capability-score.mjs',
  'app/v28/core/skill-markdown.mjs',
  'app/v28/core/card-onboarding.mjs',
  'app/v28/core/agent-alignment.mjs',
  'app/v28/core/memory-policy.mjs',
];
for (const rel of mjs) {
  const file = path.join(ROOT, rel);
  if (!existsSync(file)) { console.log('✗ 缺文件：', rel); failures += 1; continue; }
  try { execFileSync(process.execPath, ['--check', file], { stdio: 'pipe' }); }
  catch (error) { console.log('✗ 语法错误：', rel, String(error.stderr).slice(0, 160)); failures += 1; }
}

for (const rel of ['app/v28/features/pages24/index.ts', 'app/v28/features/pages24/README.md', 'services/emos-memory/README.md', 'services/skill-foundry/README.md', 'services/pa-gateway/pyproject.toml', 'tools/page2-checks', 'docs/第二页第四页-资产清单与数据契约.md']) {
  if (!existsSync(path.join(ROOT, rel))) { console.log('✗ 缺资产：', rel); failures += 1; }
}

// 副本纯净度：密钥、数据库、运行日志不许被复制进来（曾经漏过 pa-gateway.db）
const FORBIDDEN = [
  [/^\.env$/, '密钥文件'],
  [/^\.env\.(?!example|sample|template).+$/, '密钥文件'],
  [/\.(db|db-wal|db-shm|sqlite3|sqlite3-wal|sqlite3-shm)$/, '数据库'],
  [/\.(log|jsonl)$/, '运行日志'],
];
for (const file of walk(ROOT)) {
  const rel = normalize(path.relative(ROOT, file));
  if (rel.startsWith('scripts/')) continue;
  const name = path.basename(file);
  const hit = FORBIDDEN.find(([pattern]) => pattern.test(name));
  if (hit) { console.log('✗ 副本里不该有的文件：', rel, `（${hit[1]}）`); failures += 1; }
}

console.log('宿主提供（没复制，运行时由主库给）：', [...hostHits].sort().join(', ') || '（无）');
console.log(failures === 0 ? '✓ 副本自检通过' : `✗ 副本自检失败：${failures} 项`);
process.exit(failures === 0 ? 0 : 1);
