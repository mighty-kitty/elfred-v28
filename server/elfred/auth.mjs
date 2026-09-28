import { randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';
import { id, now, hash, fail } from './store.mjs';

export function passwordHash(password) {
  const salt = randomBytes(16).toString('hex');
  return salt + ':' + scryptSync(password,salt,64).toString('hex');
}
function matches(password, stored) {
  const [salt,digest] = stored.split(':');
  return timingSafeEqual(Buffer.from(digest,'hex'),scryptSync(password,salt,64));
}
export function authenticate(store, handle, password, register = false, name = '', client = 'local') {
  if(typeof handle==='string')handle=handle.trim();
  if (typeof handle !== 'string' || !/^[a-zA-Z0-9_.@+-]{3,80}$/.test(handle)) fail('INVALID_HANDLE','账号需为 3—80 位字母、数字或 _.@+-');
  if (typeof password !== 'string' || password.length < 8 || password.length > 128) fail('INVALID_PASSWORD','密码长度需为 8—128 位');
  const key = hash(client+':'+handle.toLowerCase()), time = Date.now();
  const limit = store.db.prepare('SELECT * FROM login_attempts WHERE key=?').get(key);
  if (limit && limit.until > time && limit.count >= 10) fail('RATE_LIMIT','尝试次数过多，请稍后再试',429);
  store.db.prepare('INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN until<? THEN 1 ELSE count+1 END,until=CASE WHEN until<? THEN excluded.until ELSE until END').run(key,time+900000,time,time);
  const canonical = handle.toLowerCase();
  let user = store.db.prepare('SELECT * FROM users WHERE handle=?').get(canonical);
  if (register) {
    if (user) fail('ACCOUNT_EXISTS','该账号已注册',409);
    if (typeof name !== 'string' || name.trim().length < 1 || name.length > 60) fail('INVALID_NAME','请填写 1—60 字的称呼');
    const userId = id();
    store.db.prepare('INSERT INTO users VALUES(?,?,?,?,?)').run(userId,canonical,passwordHash(password),name.trim(),now());
    user = store.db.prepare('SELECT * FROM users WHERE id=?').get(userId);
  } else if (!user || !matches(password,user.password)) fail('INVALID_LOGIN','账号或密码不正确',401);
  store.db.prepare('DELETE FROM login_attempts WHERE key=?').run(key);
  const token = randomBytes(32).toString('base64url');
  store.db.prepare('DELETE FROM sessions WHERE expires<?').run(time);
  store.db.prepare('INSERT INTO sessions VALUES(?,?,?)').run(hash(token),user.id,time+7*86400000);
  return { token, user:store.user(user.id) };
}
export function session(store, token) {
  if (!token) return null;
  const row = store.db.prepare('SELECT user_id FROM sessions WHERE token=? AND expires>?').get(hash(token),Date.now());
  return row ? store.user(row.user_id) : null;
}
