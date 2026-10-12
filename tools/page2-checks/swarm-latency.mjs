/**
 * 协作并发的 A/B 实测（真模型、真运行时）：
 *   同一批协作步骤，independent（现在并发） vs pipeline（有依赖，仍串行）。
 *   node tools/page2-checks/swarm-latency.mjs
 * 关注：端到端耗时、调用次数、tokens、receipts 阶段顺序（账目要与串行一致）。
 */
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";
const ROOT = path.resolve(import.meta.dirname, "..", "..");
const load = (rel) => import(pathToFileURL(path.join(ROOT, rel)).href);

const env = {};
for (const line of readFileSync(path.join(ROOT, ".env.local"), "utf8").split(/\r?\n/)) {
  const m = line.match(/^([A-Z0-9_]+)=(.*)$/); if (m) env[m[1]] = m[2];
}
for (const [k, v] of Object.entries(env)) if (!process.env[k]) process.env[k] = v;

const { Store, id } = await load("server/elfred/store.mjs");
const { Service } = await load("server/elfred/service.mjs");
const { Runtime } = await load("server/elfred/runtime.mjs");
const { authenticate } = await load("server/elfred/auth.mjs");
const { ModelProvider } = await load("server/elfred/providers.mjs");

const DOCS = [
  ["产品定位", "Elfred 面向个人知识工作者，把零散资料沉淀成可复用的能力。目标用户是独立创作者、小团队负责人、刚入行的执行者。"],
  ["用户反馈", "用户希望它记住偏好不要重复问；结果要能指到来源；对外展示时能控制别人看到什么。"],
  ["交付约束", "对外材料不得出现内部数据；引用需可追溯；涉及第三方要先确认授权；初稿必须本人核对。"],
  ["竞品对比", "同类产品要么纯对话不可复用，要么模板库太僵化；差异点是把过程沉淀成能力，且每步能说明依据。"],
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function run(mode) {
  const store = new Store(":memory:");
  const provider = new ModelProvider(process.env);
  const service = new Service(store, provider), runtime = new Runtime(store, provider);
  const user = authenticate(store, `bench-${mode}-${Date.now()}`, "bench-password-1", true, "bench").user;
  service.initialize(user);
  const cmd = (action, input) => service.command(user.id, `${action}-${id()}`, action, input);
  const ref = (o) => ({ id: o.id, version: store.get(o.id).version });
  const docs = DOCS.map(([title, content]) => cmd("document.create", { title: `${title}.md`, content }));
  const docRefs = docs.map(ref);

  const task = cmd("task.create", {
    goal: "先整理产品使用场景，然后做一版对外介绍材料", system: "create", mode: "compose",
    review_mode: "single", source_refs: docRefs,
  });
  cmd("task.collaboration", {
    ...ref(task), confirm: true,
    steps: [
      { id: "support-0", system: "explore", goal: "整理产品使用场景", source_refs: docRefs.slice(0, 2), depends: [] },
      { id: "support-1", system: "advise", goal: "比较两种对外介绍口径", source_refs: docRefs.slice(2, 4), depends: [] },
    ],
  });
  // 关键：只有 pipeline 才把第二步挂到第一步后面（那样就不会被并发）
  if (mode === "pipeline") {
    const current = store.get(task.id);
    cmd("task.collaboration", {
      ...ref(current), confirm: true,
      steps: [
        { id: "support-0", system: "explore", goal: "整理产品使用场景", source_refs: docRefs.slice(0, 2), depends: [] },
        { id: "support-1", system: "advise", goal: "比较两种对外介绍口径", source_refs: docRefs.slice(2, 4), depends: ["support-0"] },
      ],
    });
  }
  cmd("task.confirm", { ...ref(store.get(task.id)), confirm: true, model_consent: true });
  const started = Date.now();
  cmd("run.start", ref(store.get(task.id)));
  let elapsed = null;
  for (let i = 0; i < 300; i++) {
    await runtime.tick();
    const t = store.get(task.id);
    if (["awaiting_acceptance", "awaiting_review", "failed", "partial", "cancelled"].includes(t.data.status)) { elapsed = Date.now() - started; break; }
    await sleep(50);
  }
  const t = store.get(task.id), run = store.get(t.data.run_id);
  const receipts = (run?.data?.receipts ?? []).filter((r) => r.status === "succeeded");
  const out = {
    mode, ms: elapsed, status: t.data.status, calls: t.data.calls, tokens: t.data.tokens, units: t.data.units,
    receipts: receipts.map((r) => `${r.step_id}:${r.phase}`).join(" → "),
    withEvidence: receipts.filter((r) => (r.citations ?? []).length >= 0).length,
  };
  store.close();
  return out;
}

const independent = await run("independent");
const pipeline = await run("pipeline");
for (const r of [independent, pipeline]) {
  console.log(`${r.mode.padEnd(12)} 端到端 ${String(r.ms).padStart(6)} ms · 状态 ${r.status} · 调用 ${r.calls} 次 · tokens ${r.tokens} · units ${r.units}`);
  console.log(`              receipts: ${r.receipts}`);
}
console.log(`\n提速：${pipeline.ms && independent.ms ? (pipeline.ms / independent.ms).toFixed(2) + "×" : "（未测到）"}（pipeline/independent）`);
