/**
 * 上游服务的公共零件：地址白名单 + 一次带超时和体积上限的 JSON 调用。
 *
 * 为什么单开一个文件：记忆中枢、能力服务、规划网关、依赖状态四处原来各写了一份
 * `safeBase`（四份一样的规矩，改一处忘三处），HTTP 调用也各写各的。
 * 这些上游都是**可选依赖**，所以这里只做两件事：不把私密内容送出去、失败就说清楚。
 *
 * 规矩（跟记忆同步那条边界一致）：
 *   · 只接受 https，或本机回环地址上的 http；带账号密码 / 查询串 / 锚点的地址一律拒绝；
 *   · 每次调用都有超时；响应有体积上限（防止一个异常大的 /health 把探活判成"不可达"或吃满内存）；
 *   · **不替调用方加头**（除了明确传进来的）：上游请求里出现什么头必须是调用方写的，
 *     否则"绝不带用户身份"这条边界就没法用一行断言钉住；
 *   · 非 2xx、超大、不是 JSON —— 都抛错，错误信息里带状态码和响应片段，别让人猜。
 */

/** 上游地址白名单；不合规返回 null（调用方按"未配置"处理，不影响应用自己的功能） */
export function safeBase(value) {
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

/**
 * 调一次上游并解析 JSON。
 * @param {(input: string, init?: object) => Promise<Response>} fetcher 便于测试注入
 * @param {string} url
 * @param {{method?: string, headers?: Record<string,string>, body?: string, timeout?: number, limit?: number}} options
 * @returns {Promise<any|null>} 空响应体返回 null
 */
export async function callJson(fetcher, url, options = {}) {
  const { method = 'GET', headers = {}, body, timeout = 15000, limit = 200000 } = options;
  const response = await fetcher(url, {
    method,
    redirect: 'error',
    headers,
    ...(body === undefined ? {} : { body }),
    signal: AbortSignal.timeout(timeout),
  });
  const raw = await response.text();
  if (!response.ok) throw new Error(`${method} ${url} → HTTP ${response.status} ${raw.slice(0, 200)}`);
  if (raw.length > limit) throw new Error(`${method} ${url} → 响应过大（${raw.length} > ${limit} 字节）`);
  try {
    return raw ? JSON.parse(raw) : null;
  } catch {
    throw new Error(`${method} ${url} → 不是有效的 JSON`);
  }
}

/** 拼地址：`base` 去掉结尾斜杠再拼路径，避免出现两个斜杠 */
export const joinUrl = (base, path) => `${base.href.replace(/\/$/, '')}${path}`;
