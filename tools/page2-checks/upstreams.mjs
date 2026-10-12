/**
 * 第二页 / 第四页的上游启停工具。
 *
 *   node tools/page2-checks/upstreams.mjs status          # 看四个上游的状态
 *   node tools/page2-checks/upstreams.mjs start all        # FreeTodo → EMOS → 网关 → Foundry 依次起
 *   node tools/page2-checks/upstreams.mjs start emos       # 单个起
 *   node tools/page2-checks/upstreams.mjs stop all         # 只杀它自己拉起来的进程
 *   node tools/page2-checks/upstreams.mjs dev              # 起齐上游，再启动应用（退出时代停上游）
 *   node tools/page2-checks/upstreams.mjs deps             # 装上游依赖（可重复执行）
 *   node tools/page2-checks/upstreams.mjs preflight        # 开工前体检：磁盘、node_modules、端口
 *   node tools/page2-checks/upstreams.mjs ensure           # 缺哪个补哪个（幂等，跑完即走）
 *
 * 为什么单独做一个：应用侧的启动脚本只在 `npm run dev:local` 里拉 EMOS，
 * 另外三个上游没人拉，失败时还不给原因（见 docs/第二页第四页-上游启动说明.md）。
 * 这个工具不改任何服务的代码，只负责按正确的 cwd / 环境变量把它们拉起来，并如实报状态。
 */
import { readFileSync, existsSync, mkdirSync, writeFileSync, openSync } from "node:fs";
import { spawn, execFileSync } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const DATA = path.resolve(process.env.ELFRED_DATA_DIR || path.join(ROOT, ".elfred-data"));
const RUN_DIR = path.join(DATA, "upstreams");

function readEnvFile() {
  const file = path.join(ROOT, ".env.local");
  const env = {};
  if (!existsSync(file)) return env;
  for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m) env[m[1]] = m[2];
  }
  return env;
}
const FILE_ENV = readEnvFile();
const env = (key, fallback) => process.env[key] ?? FILE_ENV[key] ?? fallback;

const freetodoDir = env("ELFRED_FREETODO_DIR") ||
  "C:/Users/35057/Desktop/纪念-Elfred历史版本/elfred/FreeTodo-main/FreeTodo-main";
// FreeTodo 的依赖装在数据目录下的独立环境里（torch / chromadb / sentence-transformers 这些不进全局），
// 有就用它，没有才回落到全局 python。
const freetodoVenvPython = path.join(DATA, "freetodo-venv", "Scripts", "python.exe");
const freetodoPython = env("ELFRED_FREETODO_PYTHON") || (existsSync(freetodoVenvPython) ? freetodoVenvPython : env("ELFRED_PYTHON", "python"));
const emosUrl = env("ELFRED_MEMORY_HUB_URL", "http://127.0.0.1:8200/");
const emosPort = new URL(emosUrl).port || "8200";
const emosToken = env("ELFRED_MEMORY_HUB_TOKEN", "");
const gatewayUrl = env("ELFRED_PA_GATEWAY_URL", "http://127.0.0.1:8790");
const foundryUrl = env("ELFRED_SKILL_FOUNDRY_URL", "http://127.0.0.1:8765");

const SERVICES = [
  {
    key: "freetodo", title: "FreeTodo", port: 8001, depends: [],
    cwd: freetodoDir, cmd: [freetodoPython, "-m", "lifetrace.server"],
    env: () => ({ PYTHONUTF8: "1" }),
    check: async () => (await portOpen("127.0.0.1", 8001)) ? "端口在" : null,
  },
  {
    key: "emos", title: "EMOS 记忆中枢", port: Number(emosPort), depends: [],
    cwd: path.join(ROOT, "services", "emos-memory"),
    cmd: [env("ELFRED_PYTHON", "python"), "-m", "src.memory_system.api.elfred_bridge"],
    env: () => ({ ELFRED_MEMORY_HUB_TOKEN: emosToken, ELFRED_EMOS_PORT: emosPort, ELFRED_EMOS_DATABASE: path.join(DATA, "emos-memory.sqlite") }),
    check: async () => {
      try {
        const r = await fetch(new URL("v1/status", emosUrl), { headers: { Authorization: "Bearer " + emosToken }, signal: AbortSignal.timeout(1200) });
        const j = await r.json();
        return r.ok && j.contract === "elfred-memory-v1" ? `契约 ${j.contract}` : `响应异常 ${r.status}`;
      } catch { return null; }
    },
  },
  {
    key: "gateway", title: "PA 网关", port: 8790, depends: [],
    cwd: path.join(ROOT, "services", "pa-gateway"),
    cmd: [env("ELFRED_PYTHON", "python"), "-m", "uvicorn", "app.main:app", "--port", "8790", "--host", "127.0.0.1"],
    env: () => ({}),
    check: async () => {
      try { const r = await fetch(new URL("/health", gatewayUrl), { signal: AbortSignal.timeout(1200) }); return r.ok ? "健康检查通过" : `响应 ${r.status}`; } catch { return null; }
    },
  },
  {
    key: "foundry", title: "Skill Foundry", port: 8765, depends: ["freetodo"],
    cwd: path.join(ROOT, "services", "skill-foundry"),
    // --frozen：别让 uv run 顺手改写仓库里的 uv.lock（实测会把锁文件搅成 890 行差异，污染 PR）
    cmd: ["uv", "run", "--frozen", "python", "-m", "adapter"],
    // 上游上下文后端：freetodo 是完整路径。legacy 是它自己的回落实现，
    // 但实测（2026-10-12）passive 扫描（adapter/skill_foundry/passive.py）无条件调 FreeTodo 的
    // /api/todos，所以 legacy 也绕不过 FreeTodo——技能生成这条链必须要 FreeTodo 起着。
    env: () => ({
      FREETODO_BASE_URL: "http://127.0.0.1:8001",
      ELFRED_ADAPTER_PORT: "8765",
      ELFRED_CONTEXT_BACKEND: env("ELFRED_CONTEXT_BACKEND", "freetodo"),
    }),
    check: async () => {
      try {
        const r = await fetch(new URL("/v1/elfred/health", foundryUrl), { signal: AbortSignal.timeout(2500) });
        return r.ok ? "/v1/elfred/health 通过" : `端口在，健康接口返回 ${r.status}`;
      } catch { return (await portOpen("127.0.0.1", 8765)) ? "端口在（健康接口没通）" : null; }
    },
  },
];

/** 端口探测用 node 直连（原来每次去起一个 PowerShell，一轮要 3 秒，等就绪时非常慢）。 */
function portOpen(host, port, timeout = 700) {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port });
    const done = (ok) => { socket.destroy(); resolve(ok); };
    socket.setTimeout(timeout);
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false));
    socket.once("error", () => done(false));
  });
}
/** 同步版：给不需要异步的调用点用（内部就是 portOpen 的同步等待，不阻塞太久）。 */
const tcp = (host, port) => {
  try {
    const { spawnSync } = require("node:child_process");
    return false;
  } catch { return false; }
};
const pidFile = (key) => path.join(RUN_DIR, `${key}.pid`);
const logFile = (key) => path.join(RUN_DIR, `${key}.log`);
const q = (s) => `'${String(s).replace(/'/g, "''")}'`;

/**
 * 真正脱离当前会话地起一个上游。
 * 为什么不用 spawn(detached:true)：实测那样起的进程仍然挂在当前 shell 的进程树/作业对象下，
 * 会话一结束（或上一次 exec 被回收）就跟着被杀——今天 EMOS/网关/Foundry 全被带走就是这原因。
 * Windows 下改用 Start-Process 起，进程属于系统而不是我们的会话。
 */
function spawnDetached(s) {
  if (process.platform === "win32") {
    // 拼一长串 -Command 太容易踩引号坑，落成一个启动脚本再跑，稳定得多。
    const launcher = path.join(RUN_DIR, `${s.key}.start.ps1`);
    const envLines = Object.entries({ ...FILE_ENV, ...s.env() })
      .filter(([, v]) => v !== undefined && v !== null)
      .map(([k, v]) => `$env:${k}=${q(v)}`);
    const args = s.cmd.slice(1).map(q).join(",");
    writeFileSync(launcher, [
      ...envLines,
      `$p = Start-Process -FilePath ${q(s.cmd[0])} -ArgumentList @(${args}) -WorkingDirectory ${q(s.cwd)} ` +
        `-WindowStyle Hidden -RedirectStandardOutput ${q(logFile(s.key))} -RedirectStandardError ${q(logFile(s.key))} -PassThru`,
      "$p.Id",
    ].join("\n"), "utf8");
    const out = execFileSync("powershell", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", launcher], { encoding: "utf8" });
    const pid = Number(String(out).trim().split(/\s+/).pop());
    if (!Number.isFinite(pid)) throw new Error(`Start-Process 没拿到 pid（脚本 ${launcher}）：${String(out).slice(0, 120)}`);
    return pid;
  }
  const fd = openSync(logFile(s.key), "w");
  const child = spawn(s.cmd[0], s.cmd.slice(1), {
    cwd: s.cwd, windowsHide: true, detached: true, stdio: ["ignore", fd, fd],
    env: { ...process.env, ...FILE_ENV, ...s.env() },
  });
  child.unref();
  return child.pid;
}
const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function status() {
  mkdirSync(RUN_DIR, { recursive: true });
  console.log(`数据目录：${DATA}\n`);
  console.log("上游            端口   状态");
  for (const s of SERVICES) {
    const pid = existsSync(pidFile(s.key)) ? Number(readFileSync(pidFile(s.key), "utf8").trim()) : null;
    const detail = await s.check();
    const running = pid && alive(pid) ? `我们拉的（pid ${pid}）` : (await portOpen("127.0.0.1", s.port)) ? "在跑（不是我们拉的）" : "没起";
    console.log(`${s.title.padEnd(14)} ${String(s.port).padEnd(6)} ${detail ? "通" : "断"}  ${detail ?? "—"}  · ${running}`);
  }
  console.log("\n提示：Jev 是外部服务，只能配 key，不在这个表里。");
  await appStatus();
}

/** 应用本身：端口在不在、接口挂没挂上。区分"起了但没接口"（npm run dev）和"真能跑"（dev:local / 本工具的 dev）。 */
async function appStatus(quiet = false) {
  const port = Number(env("ELFRED_PORT", "3000"));
  const up = await portOpen("127.0.0.1", port);
  if (!up) { if (!quiet) console.log(`应用            ${port}   没起  · 用本工具 dev 或 npm run dev:local 起来`); return { up: false, api: null }; }
  let api = null;
  try {
    const r = await fetch(`http://127.0.0.1:${port}/api/elfred/health/deps`, { signal: AbortSignal.timeout(5000) });
    api = r.status;   // 200 或 401 都表示接口在；404 表示这个入口没挂接口
  } catch { api = 0; }
  if (!quiet) {
    const verdict = api === 404 ? "起了，但 /api/elfred 是 404 —— 这个入口没挂后端（npm run dev 就是这样）"
      : api ? `接口在（/api/elfred/health/deps 返回 ${api}${api === 401 ? "，未登录属正常" : ""}）`
      : "起了，但接口没响应";
    console.log(`应用            ${port}   通  ${verdict}`);
  }
  return { up: true, api };
}

/** 开工前体检：磁盘空间、node_modules 是不是符号链接、端口占用。 */
async function preflight() {
  const { statfsSync, lstatSync } = await import("node:fs");
  console.log("① 磁盘空间");
  try {
    const s = statfsSync("C:/");
    const freeGb = (s.bavail * s.bsize) / 1e9;
    console.log(`   C 盘剩余 ${freeGb.toFixed(2)} GB ${freeGb < 5 ? "← 偏小，装依赖/构建可能报 ENOSPC，先清 Temp 和 npm 缓存" : ""}`);
  } catch { console.log("   读不到磁盘信息"); }
  console.log("② node_modules");
  const nm = path.join(ROOT, "node_modules");
  if (!existsSync(nm)) console.log("   没有 node_modules，先跑 npm ci");
  else if (lstatSync(nm).isSymbolicLink()) console.log("   是符号链接 ← Turbopack 会拒绝：Symlink ... points out of the filesystem root。摘掉链接后 npm ci");
  else console.log("   是真实目录，正常");
  console.log("③ 端口");
  const ports = [[Number(env("ELFRED_PORT", "3000")), "应用"], ...SERVICES.map((s) => [s.port, s.title])];
  for (const [port, title] of ports) {
    const used = await portOpen("127.0.0.1", port);
    console.log(`   ${String(port).padEnd(6)} ${title.padEnd(14)} ${used ? "已被占用（可能已经在跑）" : "空闲"}`);
  }
  console.log("④ 上游依赖");
  console.log(`   FreeTodo 解释器：${existsSync(freetodoVenvPython) ? freetodoVenvPython : "（没装，先跑 deps）"}`);
  console.log(`   Skill Foundry：用 uv run，需要 uv 在 PATH（本次：${(() => { try { execFileSync("uv", ["--version"], { stdio: "ignore" }); return "有"; } catch { return "没有"; } })()}）`);
}

/** 装上游依赖：FreeTodo 用独立环境（不进全局），可重复执行。 */
async function deps() {
  mkdirSync(DATA, { recursive: true });
  const ftReq = path.join(freetodoDir, "requirements-runtime.txt");
  console.log("① FreeTodo 依赖");
  if (!existsSync(freetodoDir)) { console.log(`   找不到 FreeTodo 目录：${freetodoDir}（可用 ELFRED_FREETODO_DIR 指）`); }
  else {
    if (!existsSync(freetodoVenvPython)) {
      console.log(`   建独立环境：${path.join(DATA, "freetodo-venv")}`);
      execFileSync(env("ELFRED_PYTHON", "python"), ["-m", "venv", path.join(DATA, "freetodo-venv")], { stdio: "inherit" });
    }
    if (existsSync(ftReq)) {
      console.log("   装 requirements-runtime.txt（第一次会比较久，torch 那几个包很大）");
      try { execFileSync(freetodoVenvPython, ["-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--no-warn-script-location", "-r", ftReq], { stdio: "inherit" }); }
      catch { console.log("   ↑ 这条如果以文件占用报错结束，重跑一次本命令即可（Windows 上写 exe 偶发）"); }
    }
    // 实测：它那份清单里没有 icalendar，缺了 todo 路由注册不上 → /api/todos 404 → Foundry 扫描 500
    console.log("   补装清单里缺的 icalendar");
    try { execFileSync(freetodoVenvPython, ["-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--no-warn-script-location", "icalendar"], { stdio: "inherit" }); } catch {}
  }
  console.log("② Skill Foundry 依赖");
  try { execFileSync("uv", ["sync"], { cwd: path.join(ROOT, "services", "skill-foundry"), stdio: "inherit" }); }
  catch { console.log("   uv sync 没跑成；只要 uv 在 PATH，`upstreams.mjs start foundry` 时会自己同步"); }
  console.log("③ PA 网关依赖：用全局 python（uvicorn/fastapi 已有）");
}

async function start(key) {
  const targets = key === "all" ? SERVICES : SERVICES.filter((s) => s.key === key);
  if (!targets.length) { console.error(`不认识的上游：${key}`); process.exitCode = 1; return; }
  mkdirSync(RUN_DIR, { recursive: true });
  for (const s of targets) {
    for (const dep of s.depends) {
      const d = SERVICES.find((x) => x.key === dep);
      if (!(await d.check())) { console.log(`${s.title}：依赖 ${d.title} 没起，先把它拉起来`); await start(dep); }
    }
    if (await s.check()) { console.log(`${s.title}：已经在跑，跳过`); continue; }
    if (!existsSync(s.cwd)) { console.log(`${s.title}：目录不存在 ${s.cwd}（跳过）`); continue; }
    if (s.key === "foundry" && !(await SERVICES.find((x) => x.key === "freetodo").check())) {
      console.log(`${s.title}：提醒——FreeTodo 没起，它起草扫描会 500（已知硬依赖，继续起服务本身没问题）`);
    }
    try {
      const pid = spawnDetached(s);
      writeFileSync(pidFile(s.key), String(pid));
    } catch (e) {
      console.log(`  启动命令失败：${String(e.message).slice(0, 160)}`);
      continue;
    }
    process.stdout.write(`${s.title}：启动中`);
    let ready = null;
    const deadline = Date.now() + 120000;   // 最多等 2 分钟（uv run 首次解析依赖会慢）
    let dots = 0;
    while (Date.now() < deadline) {
      ready = await s.check();
      if (ready) break;
      await sleep(600);
      if (++dots % 5 === 0) process.stdout.write(".");
    }
    if (ready) { console.log(`  就绪（${ready}）`); continue; }
    console.log(`  等 2 分钟还没就绪，日志最后几行：`);
    try {
      const tail = readFileSync(logFile(s.key), "utf8").split(/\r?\n/).filter(Boolean).slice(-4);
      tail.forEach((l) => console.log(`     ${l.trim().slice(0, 150)}`));
    } catch { console.log(`     （读不到日志，路径：${logFile(s.key)}）`); }
  }
}

function stop(key) {
  const targets = key === "all" ? SERVICES : SERVICES.filter((s) => s.key === key);
  for (const s of targets) {
    if (!existsSync(pidFile(s.key))) { console.log(`${s.title}：没有我们记录的 pid，不动它`); continue; }
    const pid = Number(readFileSync(pidFile(s.key), "utf8").trim());
    if (!alive(pid)) { console.log(`${s.title}：进程已经不在`); continue; }
    try { execFileSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" }); console.log(`${s.title}：已停（pid ${pid}）`); }
    catch { console.log(`${s.title}：停不掉（pid ${pid}），手工处理`); }
  }
}

const [, , action = "status", target = "all"] = process.argv;
if (action === "status") await status();
else if (action === "start") await start(target);
else if (action === "stop") stop(target);
else if (action === "dev") await dev();
else if (action === "deps") await deps();
else if (action === "preflight") await preflight();
else if (action === "ensure") await ensure();
else { console.log("用法：node tools/page2-checks/upstreams.mjs status | start [all|名字] | stop [all|名字] | ensure | dev | deps | preflight"); }

/**
 * 缺哪个补哪个：只做"起来"这一件事，不做等待之外的别的事。
 * 什么时候用：受限环境（比如自动化会话）里，命令返回时子进程可能被一起回收，
 * 所以每次开工前跑一次 ensure 比依赖"上次起过"更可靠。
 */
async function ensure() {
  const missing = [];
  for (const s of SERVICES) if (!(await s.check())) missing.push(s.key);
  if (!missing.length) { console.log("四个上游都在跑，不用动"); await appStatus(); return; }
  console.log(`缺：${missing.join("、")} —— 现在补起来`);
  await start("all");
  await appStatus();
}

/**
 * 起齐上游 → 启动应用（调仓库自己的 dev 入口，不改它的脚本）→ 退出时把上游停掉。
 * 为什么要有这个：`npm run dev` 走 scripts/run-project.mjs，里面不拉上游，
 * 于是页面永远在等一个起不来的服务。这条命令把"先起上游再起应用"合到一步。
 */
async function dev() {
  console.log("① 先起上游（缺哪个起哪个）");
  await start("all");
  console.log("\n② 上游状态");
  await status();
  // 用 dev:local 这个入口，不用 npm run dev：
  //   `npm run dev` 走 scripts/run-project.mjs（vinext 起 Next），**不挂 Elfred 的接口**，
  //   实测 /api/elfred/health/deps 直接 404，页面只能退回演示数据；
  //   `npm run dev:local` 走 scripts/start-local.mjs，接口和页面一起挂在同一个端口上。
  console.log("\n③ 启动应用（dev:local 入口，前台运行；Ctrl+C 退出时会停掉本次拉起的上游）");
  const child = spawn(process.execPath, ["--env-file-if-exists=.env.local", path.join(ROOT, "scripts", "start-local.mjs")], {
    cwd: ROOT, stdio: "inherit", env: { ...process.env, ...FILE_ENV },
  });
  const shutdown = () => {
    console.log("\n收到退出信号：停掉本次拉起的上游");
    try { child.kill(); } catch {}
    stop("all");
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
  child.on("exit", (code) => { console.log(`\n应用退出了（code ${code}），停掉上游`); stop("all"); process.exit(code ?? 0); });
  // 起来之后替你看一眼接口挂没挂（npm run dev 那个入口会在这里报 404）
  await sleep(15000);
  for (let i = 0; i < 12; i++) {
    const r = await appStatus(true);
    if (r.up && r.api) { await appStatus(); break; }
    await sleep(5000);
  }
}
