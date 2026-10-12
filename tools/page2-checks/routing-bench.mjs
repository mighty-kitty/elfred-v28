/**
 * 路由建议的回归基准：12 道真实任务，按"最终交付物归谁"标答案。
 *   node tools/page2-checks/routing-bench.mjs
 * 口径：主责判错率（主动弃权不算错）；协作候选精确率 = 命中 / 给出的候选数。
 */
import { routeSuggestion } from "../../server/elfred/task-routing.mjs";

const CASES = [
  { goal: "先查一下同类产品的定价，然后写一份两页的对比材料", owner: "create", collab: ["explore"] },
  { goal: "把这三份用户反馈整理成一份结论", owner: "create", collab: [] },
  { goal: "比较一下两个方案的稳定性，告诉我该选哪个", owner: "advise", collab: [] },
  { goal: "先整理一下需求，然后去找一个能长期合作的视觉设计师", owner: "connect", collab: [] },
  { goal: "把申请材料准备好，然后提交报名", owner: "execute", collab: [] },
  { goal: "核对这些数字是否准确，最后做一份勘误表", owner: "create", collab: ["explore"] },
  { goal: "先收集对方的背景资料，最后做一次风险审查", owner: "advise", collab: ["explore"] },
  { goal: "跟进一下这个政策这两周有什么变化", owner: "explore", collab: [] },
  { goal: "整理会议结论，然后发送邮件给团队", owner: "execute", collab: ["create"] },
  { goal: "帮我找两个能一起做这个项目的开发者", owner: "connect", collab: [] },
  { goal: "把这些要点生成一张图片", owner: "create", collab: [] },
  { goal: "查一下这类活动的报名截止时间", owner: "explore", collab: [] },
];
const SYSTEMS = ["explore", "advise", "create", "connect", "execute"];
let ownerHits = 0, wrong = 0, abstain = 0;
let collabExpected = 0, collabFound = 0;
const precisions = [];
const rows = [];
for (const c of CASES) {
  const s = routeSuggestion(c.goal);
  const owner = s?.system ?? null;
  const cand = s ? [s.system, ...(s.collaborators ?? [])] : [];
  if (owner === c.owner) ownerHits++;
  else if (!owner) abstain++;
  else wrong++;
  const hit = cand.filter((x) => c.collab.includes(x) && x !== c.owner).length;
  if (cand.length) precisions.push(hit / cand.length);
  if (c.collab.length) { collabExpected++; if (hit > 0) collabFound++; }
  rows.push(`${owner === c.owner ? "OK  " : owner ? "MISS" : "弃权"} 期望 ${c.owner.padEnd(8)} 实得 ${String(owner).padEnd(8)} 候选 [${s?.collaborators?.join(",") ?? ""}]  ${c.goal}`);
}
const avg = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
console.log(rows.join("\n"));
console.log(`\n主责：命中 ${ownerHits}/${CASES.length}（${(ownerHits / CASES.length * 100).toFixed(1)}%）· 判错 ${wrong} · 主动弃权 ${abstain}`);
console.log(`判错率 ${(wrong / CASES.length * 100).toFixed(1)}%`);
console.log(`该有协作的题 ${collabExpected} 道，协作候选命中 ${collabFound} 道（原来 0 道）；平均候选精确率 ${(avg(precisions) * 100).toFixed(1)}%`);
