import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { randomUUID, createHash } from 'node:crypto';

export class DomainError extends Error {
  constructor(code, message, status = 400) { super(message); this.code = code; this.status = status; }
}
export const fail = (code, message, status) => { throw new DomainError(code, message, status); };
export const id = () => randomUUID();
export const now = () => new Date().toISOString();
export const hash = (value) => createHash('sha256').update(value).digest('hex');

export class Store {
  constructor(filename) {
    if (filename !== ':memory:') mkdirSync(path.dirname(filename), { recursive: true });
    this.db = new DatabaseSync(filename);
    if(this.db.prepare('PRAGMA user_version').get().user_version>1){this.db.close();throw new Error('数据库版本较新，拒绝降级打开；请使用匹配版本的服务');}
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;
      CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,handle TEXT UNIQUE NOT NULL,password TEXT NOT NULL,name TEXT NOT NULL,created TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY,type TEXT NOT NULL,owner TEXT NOT NULL REFERENCES users(id),space TEXT,visibility TEXT NOT NULL DEFAULT 'private',version INTEGER NOT NULL,data TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,deleted INTEGER NOT NULL DEFAULT 0);
      CREATE INDEX IF NOT EXISTS objects_type ON objects(type,owner,deleted);
      CREATE INDEX IF NOT EXISTS objects_space ON objects(space,deleted);
      CREATE TABLE IF NOT EXISTS members(space TEXT NOT NULL REFERENCES objects(id),user_id TEXT NOT NULL REFERENCES users(id),role TEXT NOT NULL,PRIMARY KEY(space,user_id));
      CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,object_id TEXT NOT NULL,kind TEXT NOT NULL,actor TEXT NOT NULL,at TEXT NOT NULL,metadata TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS commands(actor TEXT NOT NULL,key TEXT NOT NULL,digest TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(actor,key));
      CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,run_id TEXT UNIQUE NOT NULL,status TEXT NOT NULL,lease TEXT,lease_until INTEGER NOT NULL DEFAULT 0,attempt INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY,count INTEGER NOT NULL,until INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS object_versions(object_id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,at TEXT NOT NULL,PRIMARY KEY(object_id,version));
      CREATE TABLE IF NOT EXISTS unique_keys(namespace TEXT NOT NULL,key TEXT NOT NULL,object_id TEXT NOT NULL REFERENCES objects(id),PRIMARY KEY(namespace,key));
      CREATE TABLE IF NOT EXISTS read_cursors(space TEXT NOT NULL,user_id TEXT NOT NULL,seq INTEGER NOT NULL CHECK(seq>=0),PRIMARY KEY(space,user_id));
      CREATE TABLE IF NOT EXISTS member_history(space TEXT NOT NULL,user_id TEXT NOT NULL,min_seq INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(space,user_id));
      CREATE TABLE IF NOT EXISTS budget_accounts(owner TEXT PRIMARY KEY REFERENCES users(id),limit_units INTEGER NOT NULL CHECK(limit_units>=0),reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved>=0),spent INTEGER NOT NULL DEFAULT 0 CHECK(spent>=0));
      CREATE TABLE IF NOT EXISTS usage(id TEXT PRIMARY KEY,owner TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,attempt_id TEXT UNIQUE NOT NULL,reserved INTEGER NOT NULL,actual INTEGER,status TEXT NOT NULL,receipt TEXT,created TEXT NOT NULL);
      INSERT OR IGNORE INTO migrations VALUES(1,datetime('now'));
      PRAGMA user_version=1;`);
  }
  close() { this.db.close(); }
  transaction(fn) {
    this.db.exec('BEGIN IMMEDIATE');
    try { const result = fn(); this.db.exec('COMMIT'); return result; }
    catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }
  user(userId) { return this.db.prepare('SELECT id,handle,name,created FROM users WHERE id=?').get(userId); }
  get(objectId) {
    const row = this.db.prepare('SELECT * FROM objects WHERE id=? AND deleted=0').get(objectId);
    return row ? { ...row, data: JSON.parse(row.data) } : null;
  }
  list(type) {
    return this.db.prepare('SELECT id FROM objects WHERE type=? AND deleted=0 ORDER BY created DESC,id').all(type).map(row => this.get(row.id));
  }
  role(space, userId) { return this.db.prepare('SELECT role FROM members WHERE space=? AND user_id=?').get(space, userId)?.role; }
  canRead(userId, object, seen = new Set()) {
    if (!object || object.deleted) return false;
    if(object.type==='message'&&Number(object.data.seq)<(this.db.prepare('SELECT min_seq FROM member_history WHERE space=? AND user_id=?').get(object.space,userId)?.min_seq||0))return false;
    if(object.type==='project_stage'&&(!this.role(object.space,object.owner)||!['shared','superseded'].includes(object.data.status)))return false;
    if(object.type==='post'&&object.data.status==='withdrawn')return false;
    if(object.type==='comment'&&(!this.get(object.data.post_id)||this.get(object.data.post_id).data.status==='withdrawn'))return false;
    if (seen.has(object.id) || seen.size > 32) return false;
    seen.add(object.id);
    const accessSpace=object.data.access_space || (['assist','draft'].includes(object.type)?object.data.conversation_id:null);
    if (accessSpace && !this.role(accessSpace,userId)) return false;
    // Shared objects require current membership even when the departed member authored them.
    const attachmentShared=object.type==='attachment'&&['message','post'].some(type=>this.list(type).some(parent=>(parent.data.attachments||[]).some(ref=>ref.id===object.id)&&this.canRead(userId,parent,new Set(seen))));
    const allowed = attachmentShared || object.visibility === 'public' || (object.visibility === 'members'
      ? Boolean(this.role(object.space || object.id, userId))
      : object.owner === userId);
    if (!allowed) return false;
    // Private derivatives never become a bypass around source revocation.
    const lineage=[...(object.data.source_refs||[]),...(object.type==='project_stage'?object.data.dependencies||[]:[])];
    if (object.visibility !== 'public' && lineage.length) {
      for (const ref of lineage) {
        const source = this.get(ref.id);
        if (!source || (ref.version && source.version !== ref.version) || !this.canRead(userId,source,new Set(seen))) return false;
      }
    }
    return true;
  }
  read(userId, objectId, type) {
    const object = this.get(objectId);
    if (!this.canRead(userId, object) || (type && object.type !== type)) fail('NOT_FOUND', '内容不存在或当前不可访问', 404);
    return object;
  }
  owned(userId, objectId, type) {
    const object = this.read(userId, objectId, type);
    if (object.owner !== userId) fail('FORBIDDEN', '只有所有者可以执行此操作', 403);
    return object;
  }
  visible(userId, type) { return this.list(type).filter(object => this.canRead(userId, object)); }
  add(type, owner, data, options = {}) {
    const key = options.id || id(), timestamp = now();
    this.db.prepare('INSERT INTO objects(id,type,owner,space,visibility,version,data,created,updated) VALUES(?,?,?,?,?,1,?,?,?)')
      .run(key,type,owner,options.space || null,options.visibility || 'private',JSON.stringify(data),timestamp,timestamp);
    this.db.prepare('INSERT INTO object_versions VALUES(?,?,?,?)').run(key,1,JSON.stringify(data),timestamp);
    this.event(key,`${type}.created`,owner);
    return this.get(key);
  }
  update(object, data, actor, kind = `${object.type}.updated`) {
    const result = this.db.prepare('UPDATE objects SET data=?,version=version+1,updated=? WHERE id=? AND version=? AND deleted=0')
      .run(JSON.stringify(data),now(),object.id,object.version);
    if (!result.changes) fail('VERSION_CONFLICT','内容已更新，请刷新后重试',409);
    this.db.prepare('INSERT INTO object_versions VALUES(?,?,?,?)').run(object.id,object.version+1,JSON.stringify(data),now());
    this.event(object.id,kind,actor);
    return this.get(object.id);
  }
  event(objectId, kind, actor, metadata = {}) {
    this.db.prepare('INSERT INTO events(object_id,kind,actor,at,metadata) VALUES(?,?,?,?,?)').run(objectId,kind,actor,now(),JSON.stringify(metadata));
  }
  join(space, userId, role = 'member') {
    this.db.prepare('INSERT INTO members(space,user_id,role) VALUES(?,?,?) ON CONFLICT DO NOTHING').run(space,userId,role);
  }
  members(space) {
    return this.db.prepare('SELECT u.id,u.handle,u.name,m.role FROM members m JOIN users u ON u.id=m.user_id WHERE m.space=?').all(space);
  }
  unique(namespace, key, create) {
    const old = this.db.prepare('SELECT object_id FROM unique_keys WHERE namespace=? AND key=?').get(namespace,key);
    if (old) return this.get(old.object_id);
    const object = create();
    this.db.prepare('INSERT INTO unique_keys VALUES(?,?,?)').run(namespace,key,object.id);
    return object;
  }
  expect(object, version) {
    if (!Number.isInteger(version) || object.version !== version) fail('VERSION_CONFLICT','内容已更新，请刷新后重试',409);
    return object;
  }
  command(actor, key, payload, fn) {
    if (!key || key.length > 128) fail('IDEMPOTENCY_REQUIRED','请提供有效操作标识');
    return this.transaction(() => {
      const digest = hash(JSON.stringify(payload));
      const old = this.db.prepare('SELECT * FROM commands WHERE actor=? AND key=?').get(actor,key);
      if (old) {
        if (old.digest !== digest) fail('IDEMPOTENCY_CONFLICT','操作标识已用于不同内容',409);
        // Cached results contain IDs only. All reads re-check current permissions.
        return JSON.parse(old.result);
      }
      const result = fn();
      this.db.prepare('INSERT INTO commands VALUES(?,?,?,?)').run(actor,key,digest,JSON.stringify(result));
      return result;
    });
  }
}
