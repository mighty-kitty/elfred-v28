// 第二页/第四页的静态审计：把"靠人眼看容易漏"的几类问题一次扫出来。
//
// 查什么（每类都给出"为什么值得查"）：
//   ① 前端调的命令 / 接口，后端有没有人接        —— 漏接就是死按钮
//   ② 前端读的对象类型，后端有没有人写过        —— 读不到东西就是永远空态
//   ③ 危险渲染 / 危险取值                      —— XSS 与"用错 API"这类硬伤
//   ④ 乱码注释（??? ）与 TODO/FIXME             —— 之前出过一次编码事故
//   ⑤ 同一份常量/门槛定义了多处                 —— 改一处忘一处
//   ⑥ 本地存储里存了什么                        —— 别把用户数据放浏览器里
//   ⑦ 模块外没人用的导出                        —— 死接口
//
// 用法：node tools/page2-checks/audit.mjs      （只读，不改代码）
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const MODULE = path.join(ROOT, 'app/v28/features/pages24');
const walk = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
  const full = path.join(dir, entry.name);
  return entry.isDirectory() ? walk(full) : [full];
});
const rel = (file) => path.relative(ROOT, file).replace(/\\/g, '/');
const read = (file) => readFileSync(file, 'utf8');

const moduleFiles = walk(MODULE);
const sourceFiles = moduleFiles.filter((file) => /\.(ts|tsx)$/.test(file));
const moduleSource = sourceFiles.map(read).join('\n');
const serverFiles = walk(path.join(ROOT, 'server/elfred')).filter((file) => file.endsWith('.mjs'));
const serverSource = serverFiles.map(read).join('\n');
const httpSource = read(path.join(ROOT, 'server/elfred/http.mjs'));

const findings = [];
const note = (level, text) => findings.push(`[${level}] ${text}`);
const uniq = (list) => [...new Set(list)].sort();

// ① 命令 / 接口
const actionsIn = (text) => uniq([...text.matchAll(/action\s*[!=]==?\s*["']([a-z0-9_.]+)["']/g)].map((m) => m[1]));
const handled = actionsIn(serverSource);
const called = uniq([...moduleSource.matchAll(/command\(\s*["']([a-z0-9_.]+)["']/g)].map((m) => m[1])
  .concat([...moduleSource.matchAll(/activeCommand\([^)]*?["']([a-z0-9_.]+)["']/g)].map((m) => m[1])));
for (const action of called) if (!handled.includes(action)) note('P1', `前端调了没人接的命令：${action}`);

const routes = uniq([...httpSource.matchAll(/route\s*[!=]==?\s*["'`]([^"'`]+)["'`]/g)].map((m) => m[1]));
const fetched = uniq([...moduleSource.matchAll(/fetch\(\s*[`"']([^`"']+)/g)].map((m) => m[1]));
for (const url of fetched) {
  const clean = url.replace(/\$\{[^}]*\}/g, '').split('?')[0];
  const known = routes.some((route) => clean.startsWith(route.replace(/\/$/, '')) || clean.includes(route.replace('/api/elfred', '')));
  if (!known) note('P1', `前端请求了可能是死路径的接口：${url}`);
}

// ② 前端读的对象类型 vs 后端写过
const readTypes = uniq([...moduleSource.matchAll(/objects\s*\.\s*([a-z_]+)/g)].map((m) => m[1])
  .concat([...moduleSource.matchAll(/objects\[\s*["']([a-z_]+)["']\s*\]/g)].map((m) => m[1])));
for (const type of readTypes) {
  const written = new RegExp(`add\\(\\s*["']${type}["']|type:\\s*["']${type}["']|['"]${type}['"]`).test(serverSource);
  if (!written) note('P1', `前端读了 ${type}，但后端没有任何地方写过它`);
}

// ③ 危险渲染 / 取值
for (const file of sourceFiles) {
  const text = read(file);
  for (const [pattern, what] of [
    [/dangerouslySetInnerHTML/g, 'dangerouslySetInnerHTML'],
    [/\.innerHTML\s*=/g, 'innerHTML 赋值'],
    [/\beval\s*\(/g, 'eval'],
    [/new\s+Function\s*\(/g, 'new Function'],
    [/document\.write/g, 'document.write'],
  ]) {
    if (pattern.test(text)) note('P1', `${rel(file)} 用了 ${what}`);
  }
}

// ④ 乱码注释 / TODO
for (const file of moduleFiles.concat(serverFiles)) {
  const lines = read(file).split('\n');
  lines.forEach((line, index) => {
    if (/\/\/|\*/.test(line) && /\?{3,}/.test(line)) note('P2', `${rel(file)}:${index + 1} 注释疑似乱码：${line.trim().slice(0, 60)}`);
    if (/\b(TODO|FIXME|HACK|XXX)\b/.test(line)) note('P2', `${rel(file)}:${index + 1} 遗留标记：${line.trim().slice(0, 60)}`);
  });
}

// ⑤ 同一份门槛/常量定义了多处
for (const [label, pattern] of [
  ['等级门槛 [0,0,3,6,10,15]', /\[\s*0\s*,\s*0\s*,\s*3\s*,\s*6\s*,\s*10\s*,\s*15\s*\]/g],
  ['对齐门槛 [0,0,40,55,70,90,96]', /\[\s*0\s*,\s*0\s*,\s*40\s*,\s*55\s*,\s*70\s*,\s*90\s*,\s*96\s*\]/g],
]) {
  const hits = [...walk(path.join(ROOT, 'app')).filter((file) => /\.(ts|tsx|mjs)$/.test(file))]
    .filter((file) => read(file).match(pattern));
  const inModule = hits.filter((file) => rel(file).startsWith('app/v28/features/pages24/') || rel(file).includes('core/capability-score') || rel(file).includes('core/agent-alignment'));
  if (inModule.length > 1) note('P2', `${label} 定义了多处：${inModule.map(rel).join(', ')}`);
}

// ⑥ 本地存储：只看"这个 store 声明了哪些字段"，以及每次写入是不是只动这些字段。
// （不靠"字符串里有没有 content 这种词"去猜 —— 那种检查会误报，也拦不住真问题。）
const storeText = read(path.join(MODULE, 'api/page2-store.ts'));
const storedKeys = [...storeText.matchAll(/^\s{2}([a-zA-Z]+):/gm)].map((m) => m[1]);
note('INFO', `浏览器里只存这些交接字段：${storedKeys.join(', ')}`);
for (const risky of ['content', 'title', 'name', 'bio', 'tags', 'memory', 'avatar', 'cover', 'email', 'phone']) {
  if (storedKeys.includes(risky)) note('P1', `本地存储里出现了用户内容字段：${risky}`);
}
const writes = [...storeText.matchAll(/writePage2\(\{([^}]*)\}/g)].map((m) => m[1]);
for (const write of writes) {
  const keys = [...write.matchAll(/([a-zA-Z]+)\s*:/g)].map((m) => m[1]);
  for (const key of keys) if (!storedKeys.includes(key) && key !== 'pendingCard' && key !== 'pendingSkill') {
    note('P1', `page2-store 写了未声明的字段：${key}`);
  }
}

// ⑦ 模块外没人用的导出（只查 index.ts 门面）
const facade = read(path.join(MODULE, 'index.ts'));
const facadeExports = uniq([...facade.matchAll(/export\s+(?:type\s+)?\{([^}]+)\}/g)].flatMap((m) => m[1].split(',').map((item) => item.trim().split(/\s+as\s+/).pop())));
const outside = walk(path.join(ROOT, 'app')).filter((file) => /\.(ts|tsx)$/.test(file) && !rel(file).startsWith('app/v28/features/pages24/'));
const outsideSource = outside.map(read).join('\n');
for (const name of facadeExports) {
  if (!name) continue;
  if (!new RegExp(`\\b${name}\\b`).test(outsideSource)) note('P3', `门面导出但模块外没人用：${name}`);
}

console.log(`扫了 ${sourceFiles.length} 个前端文件 / ${serverFiles.length} 个后端文件\n`);
const order = { P1: 0, P2: 1, P3: 2, INFO: 3 };
findings.sort((a, b) => order[a.slice(1, 3)] - order[b.slice(1, 3)]);
for (const line of findings) console.log('  ' + line);
const blockers = findings.filter((line) => line.startsWith('[P1]'));
console.log(blockers.length ? `\n✗ P1 ${blockers.length} 条需要处理` : '\n✓ 没有 P1 级问题');
process.exit(blockers.length ? 1 : 0);
