// CSS Modules 体检：逐个样式文件算"定义了但没人用"和"用了但没定义"。
//
// 为什么需要它：knowledge.module.css 近 2000 行，被 11 个组件 + 6 个屏共用；
// 删了组件忘了删样式、改了类名忘了改引用，两边都不会报错 —— 只能靠这种清点。
// 归属按"这个文件导入了哪个样式模块"算，不是把全模块的类混在一起比。
// 用法：node tools/page2-checks/css-classes.mjs
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const MODULE = path.join(ROOT, 'app/v28/features/pages24');

const walk = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
  const full = path.join(dir, entry.name);
  return entry.isDirectory() ? walk(full) : [full];
});
const rel = (file) => path.relative(ROOT, file).replace(/\\/g, '/');

const files = walk(MODULE);
const cssFiles = files.filter((file) => file.endsWith('.module.css'));
const sourceFiles = files.filter((file) => /\.tsx?$/.test(file));

/** 一个样式文件里**本模块**定义的类名（`:global(...)` 里的是全局类，不算） */
function definedClasses(text) {
  const withoutComments = text.replace(/\/\*[\s\S]*?\*\//g, '');
  const withoutGlobals = withoutComments.replace(/:global\([^)]*\)/g, '');
  const names = new Set();
  for (const match of withoutGlobals.matchAll(/\.(-?[A-Za-z_][\w-]*)/g)) names.add(match[1]);
  return names;
}

/** 每个源文件里 `import <别名> from "<某个 module.css>"` 的别名，以及用别名引用的类名 */
function usageByModule() {
  const used = new Map();
  for (const file of sourceFiles) {
    const text = readFileSync(file, 'utf8');
    const aliases = new Map();
    for (const match of text.matchAll(/import\s+([A-Za-z_$][\w$]*)\s+from\s+["']([^"']+\.module\.css)["']/g)) {
      const target = path.resolve(path.dirname(file), match[2]);
      if (!aliases.has(target)) aliases.set(target, []);
      aliases.get(target).push(match[1]);
    }
    for (const [target, names] of aliases) {
      if (!used.has(target)) used.set(target, new Set());
      for (const alias of names) {
        for (const match of text.matchAll(new RegExp(`${alias}\\.([A-Za-z_$][\\w$]*)`, 'g'))) used.get(target).add(match[1]);
        for (const match of text.matchAll(new RegExp(`${alias}\\[\\s*["']([^"']+)["']\\s*\\]`, 'g'))) used.get(target).add(match[1]);
      }
    }
  }
  return used;
}

const used = usageByModule();
let problems = 0;
for (const css of cssFiles) {
  const defined = definedClasses(readFileSync(css, 'utf8'));
  const referenced = used.get(css) ?? new Set();
  const unused = [...defined].filter((name) => !referenced.has(name));
  const missing = [...referenced].filter((name) => !defined.has(name));
  console.log(`${rel(css)}：定义 ${defined.size} 个类，被 ${referenced.size} 个类引用`);
  if (unused.length) { console.log(`  没有人用（${unused.length}）：${unused.join(', ')}`); problems += unused.length; }
  if (missing.length) { console.log(`  用了但没定义（${missing.length}）：${missing.join(', ')}`); problems += missing.length; }
}
console.log(problems ? `\n共 ${problems} 处需要处理` : '\n✓ CSS 类都对得上');
process.exit(problems ? 1 : 0);
