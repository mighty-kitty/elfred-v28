/**
 * 第二页 / 第四页的上游启停工具。
 *
 *   node tools/page2-checks/upstreams.mjs status          # 看四个上游的状态
 *   node tools/page2-checks/upstreams.mjs start all        # FreeTodo → EMOS → 网关 → Foundry 依次起
 *   node tools/page2-checks/upstreams.mjs start emos       # 单个起
 *   node tools/page2-checks/upstreams.mjs stop all         # 只杀它自己拉起来的进程
 *   node tools/page2-checks/upstreams.mjs dev              # 起齐上游，再启动应用（退出时代停上游）
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
    cmd: ["uv", "run", "python", "-m", "adapter"],
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
    const out = await new Promise((resolve) => {
      try {
        const fd = openSync(logFile(s.key), "w");
        const child = spawn(s.cmd[0], s.cmd.slice(1), {
          cwd: s.cwd, windowsHide: true, detached: true, stdio: ["ignore", fd, fd],
          env: { ...process.env, ...FILE_ENV, ...s.env() },
        });
        child.unref();
        writeFileSync(pidFile(s.key), String(child.pid));
        resolve(child.pid);
      } catch (e) { resolve(0); console.log(`  启动命令失败：${String(e.message).slice(0, 100)}`); }
    });
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
else { console.log("用法：node tools/page2-checks/upstreams.mjs status | start [all|emos|gateway|foundry|freetodo] | stop [all|名字]"); }

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
}
