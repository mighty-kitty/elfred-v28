// 三个上游服务（都在本仓库 services/ 下）是**可选**依赖：配了地址就探一下，没配就如实说"尚未配置"。
// 只做健康检查与本地统计，私密记忆内容不经过这条边界，也不会带着客户端选定的身份头走。
//
// ⚠️ 探活 ≠ 用上了。每一项除了 ok，还带：
//   used         有没有**真实调用过**（不是探活，是真的有回执）
//   last_used_at 最近一次真实回执时间
//   evidence     证据是什么（同步了几条 / 还是"从来没有调用过"）
// 设置页据此显示"未使用过 / 最近用过"，避免把"服务可达"说成"已经在用"。
// 每个探测单独 4 秒超时、并发跑：任一上游挂了都不影响其它项，也不影响本应用自己的功能。
// （4 秒不是随手写的：能力服务自己会去问它的上游，健康检查正常也要 2 秒出头。）
const SERVICES = [
  {
    key: 'emos',
    env: 'ELFRED_MEMORY_HUB_URL',
    path: '/health',
    configured: ['独立记忆服务可达', '服务可达；记忆同步状态以同步回执为准'],
    missing: ['尚未配置独立记忆服务', '当前记忆保存在应用数据库，跨服务同步尚未配置'],
    down: ['独立记忆服务不可达', '应用内记忆仍可使用，未同步到记忆中枢'],
  },
  {
    key: 'skill_foundry',
    env: 'ELFRED_SKILL_FOUNDRY_URL',
    path: '/v1/elfred/health',
    configured: ['独立能力服务可达', '服务可达；当前仍使用应用内已保存的工具'],
    missing: ['尚未配置独立能力服务', '当前使用应用内已保存的工具与专业能力，独立能力服务尚未配置'],
    down: ['独立能力服务不可达', '当前仍使用应用内能力'],
  },
  {
    key: 'gateway',
    env: 'ELFRED_PA_GATEWAY_URL',
    path: '/health',
    configured: ['独立规划网关可达', '服务可达；多步骤任务先由它出方案，落不成可执行步骤时回落应用内运行时'],
    missing: ['尚未配置独立规划网关', '当前任务由应用内运行时执行，独立规划网关尚未配置'],
    down: ['独立规划网关不可达', '当前任务由应用内运行时执行'],
  },
];

const status = (ok, words) => ({ ok, reason: words[0], impact: words[1], used: false, last_used_at: null, evidence: '' });
const INVALID = ['上游地址不合规（需要 https 或本机回环地址）', '已按未配置处理，应用内功能不受影响'];

/** EMOS 的真实使用证据：`memory_bridge` 里同步成功过几条、最近一次是什么时候。 */
function emosUsage(store, user, config) {
  const events = store.list('memory_bridge').filter((item) => item.owner === user);
  const synced = events.filter((item) => item.data.status === 'synced');
  const pending = events.filter((item) => item.data.status === 'pending').length;
  const last = synced.map((item) => item.data.synced_at).filter(Boolean).sort().pop() || null;
  if (!config.ELFRED_MEMORY_HUB_TOKEN) return { used: false, last_used_at: null, evidence: '未配置服务端令牌（ELFRED_MEMORY_HUB_TOKEN），记忆只存在应用数据库里' };
  if (synced.length === 0) return { used: false, last_used_at: null, evidence: `还没有同步过；当前待同步 ${pending} 条` };
  return { used: true, last_used_at: last, evidence: `已同步 ${synced.length} 条${pending ? `，待同步 ${pending} 条` : ''}` };
}

import {forgeUsage} from './skill-forge/index.mjs';
import {gatewayUsage} from './pa-gateway/index.mjs';
import {jevUsage} from './jev-verdict/index.mjs';
import {safeBase, callJson, joinUrl} from './upstream.mjs';

const UNUSED = {
  skill_foundry: '产品还没有调用它生成 skill；当前能力卡来自应用内工具库与任务沉淀',
  gateway: '任务仍由应用内运行时规划；还没有把规划交给它',
};

/** 探活：地址不合规返回 null（按"未配置"处理）；连不上、非 2xx、超大、自报 degraded 都算不可达 */
async function probe(value, path, fetcher) {
  const base = safeBase(value);
  if (!base) return null;
  // 200KB：能力服务的 /health 会带整份上游状态（实测 45KB），20KB 的旧上限会把"健康"判成"不可达"。
  const result = await callJson(fetcher, joinUrl(base, path), { timeout: 4000, limit: 200000, headers: { Accept: 'application/json' } });
  if (result?.status === 'degraded' || result?.status === 'error' || result?.ok === false) throw new Error('degraded');
  return true;
}

/** 老部署把这三个状态挂在独立服务上：只有在某一项没有直连地址时才去问它一次。 */
async function relayDeps(config, fetcher) {
  const base = safeBase(config.ELFRED_PAGE2_API_URL);
  if (!base) return null;
  try {
    return await callJson(fetcher, joinUrl(base, '/health/deps'), {
      timeout: 3000,
      limit: 100000,
      headers: config.ELFRED_PAGE2_API_TOKEN ? { Authorization: `Bearer ${config.ELFRED_PAGE2_API_TOKEN}` } : {},
    });
  } catch {
    return null;
  }
}

export async function dependencyHealth(store, provider, user, config = process.env, fetcher = fetch) {
  const memories = store.visible(user, 'memory');
  store.db.prepare('SELECT 1').get();
  const result = {
    allGreen: false,
    memory: { ok: true, count: memories.length, reason: '应用记忆库已连接' },
    emos: status(false, SERVICES[0].missing),
    skill_foundry: status(false, SERVICES[1].missing),
    gateway: status(false, SERVICES[2].missing),
    jev: { configured: provider.status().jev === 'configured', baseUrl: '', model: '', hint: '以真实服务端配置为准', ...jevUsage(store, user) },
  };

  const relay = SERVICES.some((service) => !config[service.env]) && config.ELFRED_PAGE2_API_URL ? await relayDeps(config, fetcher) : null;

  await Promise.all(SERVICES.map(async (service) => {
    if (!config[service.env]) {
      const reported = relay?.[service.key];
      result[service.key] = reported && typeof reported.ok === 'boolean'
        ? { ok: reported.ok, reason: String(reported.reason || service.missing[0]), impact: String(reported.impact ?? service.missing[1]) }
        : status(false, service.missing);
    } else {
      try {
        const reachable = await probe(config[service.env], service.path, fetcher);
        result[service.key] = reachable ? status(true, service.configured) : status(false, INVALID);
      } catch {
        result[service.key] = status(false, service.down);
      }
    }
    // 使用情况单独算：探活通过 ≠ 用上了
    Object.assign(
      result[service.key],
      service.key === 'emos'
        ? emosUsage(store, user, config)
        : service.key === 'skill_foundry'
          ? forgeUsage(store, user)
          : service.key === 'gateway'
            ? gatewayUsage(store, user)
            : { used: false, last_used_at: null, evidence: UNUSED[service.key] },
    );
  }));

  result.allGreen = result.emos.ok && result.skill_foundry.ok && result.gateway.ok;
  return result;
}
