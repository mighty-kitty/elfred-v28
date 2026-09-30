// 生成第二/四页定向工作副本：把主库里这两页的前后端 + 直接依赖 + 三个上游源码
// 同步到 C:\Users\35057\Desktop\elfred-pages24。
//
// 只读主库、只在副本里写。副本必须"干净"：不带密钥、不带数据库、不带运行日志。
// 用法：node tools/pages24-extract/extract.mjs [--dest <路径>]
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, '../../');
const argv = process.argv.slice(2);
const destFlag = argv.indexOf('--dest');
const DST = destFlag >= 0 ? path.resolve(argv[destFlag + 1]) : 'C:/Users/35057/Desktop/elfred-pages24';

const COPY = [
  'app/v28/features/pages24',
  'app/v28/core/dimensions.mjs',
  'app/v28/core/capability-score.mjs',
  'app/v28/core/skill-markdown.mjs',
  'app/v28/core/card-onboarding.mjs',
  'app/v28/core/agent-alignment.mjs',
  'app/v28/core/memory-policy.mjs',
  'app/v28/core/screen.ts',
  'app/v28/core/display-labels.ts',
  'app/v28/core/page2-identity.tsx',
  'app/v28/features/live/types.ts',
  'server/elfred/questionnaire',
  'server/elfred/profile-stats',
  'server/elfred/skill-forge',
  'server/elfred/pa-gateway',
  'server/elfred/jev-verdict',
  'server/elfred/card-onboarding',
  'server/elfred/dependency-health.mjs',
  'server/elfred/upstream.mjs',
  'server/elfred/runtime.mjs',
  'server/elfred/memory-hub.mjs',
  'server/elfred/memory-learning.mjs',
  'server/elfred/service.mjs',
  'server/elfred/http.mjs',
  'server/elfred/store.mjs',
  'services',
  'tools/page2-checks',
  'tests/elfred/questionnaire.test.mjs',
  'tests/elfred/dependency-health.test.mjs',
  'tests/elfred/memory-hub-sync.test.mjs',
  'tests/elfred/skill-forge.test.mjs',
  'tests/elfred/pa-gateway.test.mjs',
  'tests/elfred/jev-verdict.test.mjs',
  'tests/elfred/pages24-scoring.test.mjs',
  'tests/elfred/pages24-projection.test.mjs',
  'tests/elfred/upstream.test.mjs',
  'tests/elfred/card-onboarding.test.mjs',
  'docs/第二页第四页-资产清单与数据契约.md',
  'docs/第二页第四页-上游接线状态.md',
  'tools/pages24-extract/README.md',
  'tools/pages24-extract/check-extract.mjs',
  'tools/pages24-extract/check-submit.mjs',
];

const MAP = {
  'tools/pages24-extract/README.md': 'README.md',
  'tools/pages24-extract/check-extract.mjs': 'scripts/check-extract.mjs',
  'tools/pages24-extract/check-submit.mjs': 'scripts/check-submit.mjs',
};

/** 目录整棵跳过（任何位置） */
const SKIP_DIRS = new Set([
  'node_modules', '.venv', 'venv', '__pycache__', '.next', '.git', '.sites-runtime', '.wrangler',
  '.pytest_cache', '.ruff_cache', '.mypy_cache', 'dist', 'build', '.turbo',
]);

/** 只在上游服务目录里跳过的运行产物（pages24 自己的 data/ 是源码，必须带） */
const SERVICE_RUNTIME_DIRS = new Set(['data', 'logs']);

/** 文件跳过：密钥、数据库、运行日志、缓存 */
const skipFile = (name) => {
  if (name === '.env.example' || name === '.env.sample' || name === '.env.template') return false;
  if (name === '.env' || /^\.env\./.test(name)) return true;
  if (/\.(db|db-wal|db-shm|sqlite3|sqlite3-wal|sqlite3-shm)$/.test(name)) return true;
  if (/\.(log|log\.\d+|jsonl)$/.test(name)) return true;
  if (/\.(pyc|pyo)$/.test(name) || name === '.DS_Store') return true;
  return false;
};

let files = 0;
let bytes = 0;
let skipped = 0;

const walk = (from, to, inServices = false) => {
  mkdirSync(to, { recursive: true });
  for (const entry of readdirSync(from, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      const underServices = inServices || entry.name === 'services';
      if (SKIP_DIRS.has(entry.name)) { skipped += 1; continue; }
      if (underServices && SERVICE_RUNTIME_DIRS.has(entry.name)) { skipped += 1; continue; }
      walk(path.join(from, entry.name), path.join(to, entry.name), underServices);
      continue;
    }
    if (skipFile(entry.name)) { skipped += 1; continue; }
    const source = path.join(from, entry.name);
    const target = path.join(to, entry.name);
    mkdirSync(path.dirname(target), { recursive: true });
    copyFileSync(source, target);
    files += 1;
    bytes += statSync(source).size;
  }
};

rmSync(DST, { recursive: true, force: true });

const missing = [];
for (const rel of COPY) {
  const from = path.join(SRC, rel);
  if (!existsSync(from)) { missing.push(rel); continue; }
  if (statSync(from).isDirectory()) {
    const before = files;
    walk(from, path.join(DST, rel));
    console.log(`  目录  ${rel.padEnd(52)} ${String(files - before).padStart(4)} 个文件`);
    continue;
  }
  const target = path.join(DST, MAP[rel] ?? rel);
  mkdirSync(path.dirname(target), { recursive: true });
  copyFileSync(from, target);
  files += 1;
  bytes += statSync(from).size;
  console.log(`  文件  ${rel}`);
}

if (missing.length > 0) {
  console.log('\n  主库里没有（跳过）：');
  for (const rel of missing) console.log(`    · ${rel}`);
}
console.log(`\n合计 ${files} 个文件，${(bytes / 1024 / 1024).toFixed(2)} MB，跳过 ${skipped} 项 → ${DST}`);
