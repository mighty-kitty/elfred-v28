// 三个上游服务（都在本仓库 services/ 下）是**可选**依赖：配了地址就探一下，没配就如实说"尚未配置"。
// 只做健康检查，私密记忆内容不经过这条边界，也不会带着客户端选定的身份头走。
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
    configured: ['独立规划网关可达', '服务可达；当前任务由应用内运行时执行'],
    missing: ['尚未配置独立规划网关', '当前任务由应用内运行时执行，独立规划网关尚未配置'],
    down: ['独立规划网关不可达', '当前任务由应用内运行时执行'],
  },
];

const status = (ok, words) => ({ ok, reason: words[0], impact: words[1] });
const INVALID = ['上游地址不合规（需要 https 或本机回环地址）', '已按未配置处理，应用内功能不受影响'];

/** 只接受 https，或回环地址上的 http —— 与记忆同步那条边界用同一条规矩。 */
function safeBase(value) {
  try {
    const base = new URL(String(value));
    if (base.username || base.password || base.search || base.hash) return null;
    if (base.protocol === 'https:') return base;
    if (base.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)) return base;
    return null;
  } catch {
    return null;
  }
}

async function probe(value, path, fetcher) {
  const base = safeBase(value);
  if (!base) return null;
  const response = await fetcher(base.href.replace(/\/$/, '') + path, { redirect: 'error', signal: AbortSignal.timeout(4000), headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error('unhealthy');
  const raw = await response.text();
  if (raw.length > 20000) throw new Error('oversized');
  const result=JSON.parse(raw);
  if(result.status==='degraded'||result.status==='error'||result.ok===false)throw new Error('degraded');
  return true;
}

/** 老部署把这三个状态挂在独立服务上：只有在某一项没有直连地址时才去问它一次。 */
async function relayDeps(config, fetcher) {
  const base = safeBase(config.ELFRED_PAGE2_API_URL);
  if (!base) return null;
  try {
    const response = await fetcher(base.href.replace(/\/$/, '') + '/health/deps', {
      redirect: 'error', signal: AbortSignal.timeout(3000),
      headers: config.ELFRED_PAGE2_API_TOKEN ? { Authorization: `Bearer ${config.ELFRED_PAGE2_API_TOKEN}` } : {},
    });
    if (!response.ok) return null;
    const raw = await response.text();
    if (raw.length > 100000) return null;
    return JSON.parse(raw);
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
    jev: { configured: provider.status().jev === 'configured', baseUrl: '', model: '', hint: '以真实服务端配置为准' },
  };

  const relay = SERVICES.some((service) => !config[service.env]) && config.ELFRED_PAGE2_API_URL ? await relayDeps(config, fetcher) : null;

  await Promise.all(SERVICES.map(async (service) => {
    if (!config[service.env]) {
      const reported = relay?.[service.key];
      result[service.key] = reported && typeof reported.ok === 'boolean'
        ? { ok: reported.ok, reason: String(reported.reason || service.missing[0]), impact: String(reported.impact ?? service.missing[1]) }
        : status(false, service.missing);
      return;
    }
    try {
      const reachable = await probe(config[service.env], service.path, fetcher);
      result[service.key] = reachable ? status(true, service.configured) : status(false, INVALID);
    } catch {
      result[service.key] = status(false, service.down);
    }
  }));

  result.allGreen = result.emos.ok && result.skill_foundry.ok && result.gateway.ok;
  return result;
}
