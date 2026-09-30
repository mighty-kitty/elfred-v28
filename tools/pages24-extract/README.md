# 第二页 / 第四页 · 定向工作副本

这个文件夹只装**第二页（能力库 / 记忆库）**和**第四页（我的 / 个人主页）**的前后端资产，
外加它们要用的三个上游模块。第一页、第三页、登录注册、社区页面**不在**这里。

来源：`C:\Users\35057\Desktop\elfred-v28-main`（同事 main 的最新后端 + 我们这两页的改动）。
目录结构与主库一一对应，改完可以按同样的路径回填主库。

## 里面有什么

| 路径 | 是什么 |
| --- | --- |
| `app/v28/features/pages24/` | 这两页的前端模块（唯一入口 `index.ts`；screens / parts / data / api / styles） |
| `app/v28/core/dimensions.mjs` | 轻量测试的题库、计分、五维估计（前后端共用同一份） |
| `app/v28/core/agent-alignment.mjs` · `memory-policy.mjs` | 领域对齐与记忆分组（共用） |
| `app/v28/core/screen.ts` · `display-labels.ts` · `page2-identity.tsx` | 路由类型、显示文案规则、把会话快照推进模块的挂件 |
| `app/v28/features/live/types.ts` | 快照 / 实体类型 |
| `server/elfred/questionnaire/` | 轻量测试模块（题面视图、计分落库、命令） |
| `server/elfred/profile-stats/` | 主页聚合模块：关注 / 粉丝 / 获赞 + 勋章（服务端算，前端只读） |
| `server/elfred/dependency-health.mjs` | 上游服务状态：探活 + "有没有真用上"（used / last_used_at / evidence） |
| `server/elfred/service.mjs` · `http.mjs` · `store.mjs` | 宿主接缝（命令注册、路由、对象库）——只读参考 |
| `services/` | EMOS 记忆中枢 · Skill Foundry · PA 网关（源码级） |
| `tools/page2-checks/` | 实机检查 `live-audit.mjs`（真浏览器跑第二/四页，9 项断言 + 截图；旧的 40 个一次性探针已归档到纪念文件夹） |
| `tests/elfred/` | 问卷与依赖状态的测试 |
| `docs/第二页第四页-资产清单与数据契约.md` | 资产清单 + 数据契约 |

## 怎么用

1. 在主库里生成/刷新副本：`node tools/pages24-extract/extract.mjs`（只读主库、只写副本；
   密钥、数据库、运行日志和 `services/*/data` 一律不带过去）。
2. 自检：在副本里跑 `node scripts/check-extract.mjs`（含"副本里不该有密钥/数据库/日志"这一条）。
3. 交人之前：在副本里跑 `node scripts/check-submit.mjs`，确认要提交的东西一个都不少（上游源码也在）。
4. 回填主库：按同样路径复制回 `elfred-v28-main`，跑 `npm test` / `npm run test:runtime` / `npx tsc --noEmit`。

## 它不是能单独跑起来的应用

这两页挂在宿主应用上（V28 外壳、登录会话、SQLite 对象库）。下面这些**没有**复制进来，
运行仍需要主库：`app/v28/legacy/legacy-ui.tsx`、`app/v28/core/runtime-context.tsx`、
`app/v28/core/runtime-panels.tsx`、`app/v27-7-state.ts`、`app/v28/features/home/memory-governance*`。
自检脚本会把这类依赖标成「宿主提供」。
