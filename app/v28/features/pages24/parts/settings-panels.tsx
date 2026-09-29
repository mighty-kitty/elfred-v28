"use client";
import {displayTitle} from "../../../core/display-labels";

// 设置里那五个面板（账号 / 通知 / 隐私 / 数据 / 帮助）。
//
// 为什么自己写一份：`core/runtime-panels` 这份文件**只在整合版那份仓库里**（同事的主应用里），
// 我们单独跑的那份没有它 —— 而这两页要在两个仓库都能编过。所以这里用
// "结构化类型 + runtime prop" 自己实现，**命令还是走同事那套**
// （settings.save / profile.publish / approval.revoke / budget.set / task.restore），
// 不另起一套后端。
//
// 规矩：每个能点的东西都要真的改到东西；改不了就只显示状态（不做假开关）。

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import type { Screen } from "../../../core/screen";
import { ConnectedSettings } from "../../../core/runtime-panels";
import styles from "../styles/settings.module.css";

type Entity = { id: string; version?: number; data?: Record<string, unknown> };
type Snapshot = {
  user?: { name?: string; handle?: string };
  objects?: Record<string, Entity[]>;
  provider?: { configured?: boolean; model?: string | null; judge?: string; jev?: string };
  budget?: { limit_units?: number; spent?: number; reserved?: number };
};
type Runtime = {
  snapshot?: Snapshot | null;
  command?: (action: string, input: Record<string, unknown>) => Promise<unknown>;
};

export type SettingsPanelKey = "account" | "notifications" | "privacy" | "data" | "help";

const text = (item: Entity | undefined, key: string) => String(item?.data?.[key] ?? "");
const ref = (item: Entity) => ({ id: item.id, version: item.version ?? 0 });

export function SettingsPanel({
  panel,
  runtime,
  go,
  notify,
}: {
  panel: SettingsPanelKey;
  runtime?: unknown;
  go: (screen: Screen) => void;
  notify: (text: string) => void;
}) {
  const service = runtime as Runtime | undefined;
  const snapshot = service?.snapshot ?? null;
  if (!service?.command || !snapshot?.objects) {
    return (
      <p className={styles.confirmNote}>
        这一项要连上 Elfred 主服务才能改。你现在跑的是本地预览版 ——
        它只读本地那份数据，不会假装已经保存。
      </p>
    );
  }
  const run = (action: string, input: Record<string, unknown>, done: string) => {
    void service.command?.(action, input)
      .then(() => notify(done))
      .catch(() => notify("没改成，稍后再试"));
  };

  if (panel === "account") return <AccountPanel snapshot={snapshot} run={run} />;
  if (panel === "notifications") return <NotificationsPanel snapshot={snapshot} run={run} />;
  if (panel === "privacy") return <PrivacyPanel snapshot={snapshot} run={run} />;
  if (panel === "data") return <ConnectedSettings active="data" go={go} />;
  return (
    <div className={styles.panelList}>
      <p className={styles.confirmNote}>
        资料保存在运行 Elfred 的服务器数据库中。模型只接收本次授权资料。想导出一份数据，去「数据与额度 → 导出」；
        想让它少记一点，直接去「记忆与理解」删掉那条就行。有问题就在「我的 Elfred」里说一句。
      </p>
      <button type="button" className={styles.panelAction} onClick={() => go({ name: "memory" })}>
        去看它记住了什么
        <ChevronRight size={16} />
      </button>
    </div>
  );
}

function AccountPanel({
  snapshot,
  run,
}: {
  snapshot: Snapshot;
  run: (action: string, input: Record<string, unknown>, done: string) => void;
}) {
  const settings = snapshot.objects?.settings?.[0];
  const [zone, setZone] = useState(text(settings, "timezone"));
  return (
    <div className={styles.panelList}>
      <p className={styles.confirmNote}>
        {snapshot.user?.name || "还没有名字"} · @{String(snapshot.user?.handle || "").replace(/^@/, "")}
        <br />
        账号密码登录，当前会话最长七天；昵称、简介和标签在「编辑资料」里改。
      </p>
      <label className={styles.panelField}>
        <span>时区</span>
        <input value={zone} onChange={(event) => setZone(event.target.value)} placeholder="Asia/Shanghai" />
      </label>
      <button
        type="button"
        className={styles.panelAction}
        disabled={!settings || !zone.trim()}
        onClick={() => settings && run("settings.save", { ...ref(settings), ...settings.data, timezone: zone.trim() },
                                        "时区已保存")}
      >
        保存时区
      </button>
    </div>
  );
}

function NotificationsPanel({
  snapshot,
  run,
}: {
  snapshot: Snapshot;
  run: (action: string, input: Record<string, unknown>, done: string) => void;
}) {
  const settings = snapshot.objects?.settings?.[0];
  const on = settings?.data?.notifications === true;
  const quiet = settings?.data?.quiet === true;
  return (
    <div className={styles.panelList}>
      <p className={styles.confirmNote}>只管站内提醒；手机系统通知由系统设置管，这里不动它。</p>
      <button
        type="button"
        className={styles.panelAction}
        disabled={!settings}
        onClick={() => settings && run("settings.save", { ...ref(settings), ...settings.data, notifications: !on },
                                        on ? "已关闭站内提醒" : "已开启站内提醒")}
      >
        {on ? "关闭站内提醒" : "开启站内提醒"}
        <em>{on ? "当前：开启" : "当前：关闭"}</em>
      </button>
      <button
        type="button"
        className={styles.panelAction}
        disabled={!settings}
        onClick={() => settings && run("settings.save", { ...ref(settings), ...settings.data, quiet: !quiet },
                                        quiet ? "已关闭免打扰" : "已开启免打扰")}
      >
        {quiet ? "关闭免打扰" : "开启免打扰"}
        <em>{quiet ? "当前：开启" : "当前：关闭"}</em>
      </button>
    </div>
  );
}

function PrivacyPanel({
  snapshot,
  run,
}: {
  snapshot: Snapshot;
  run: (action: string, input: Record<string, unknown>, done: string) => void;
}) {
  const profile = snapshot.objects?.profile?.[0];
  const published = profile?.data?.public === true;
  const approvals = (snapshot.objects?.approval ?? []).filter((item) => text(item, "status") === "approved");
  return (
    <div className={styles.panelList}>
      <p className={styles.confirmNote}>
        当前：{published ? "公开（别人只看得到称呼和简介）" : "仅自己可见"}。
        私人记忆、任务和对话，任何情况下都不会出现在主页上。
      </p>
      <button
        type="button"
        className={styles.panelAction}
        disabled={!profile}
        onClick={() => profile && run("profile.publish", { ...ref(profile), confirm: true, publish: !published },
                                      published ? "主页已设为仅自己可见" : "主页已公开（只含称呼与简介）")}
      >
        {published ? "设为仅自己可见" : "确认公开称呼和简介"}
      </button>
      <h3 className={styles.panelTitle}>任务授权（{approvals.length}）</h3>
      {approvals.length === 0 ? (
        <p className={styles.confirmNote}>还没有给过长期授权 —— 每次动手都会先问你。</p>
      ) : (
        approvals.map((item) => (
          <button
            type="button"
            key={item.id}
            className={styles.panelAction}
            onClick={() => run("approval.revoke", ref(item), "已撤销这条授权")}
          >
            {String(item.data?.scopes ?? "一次授权")}
            <em>撤销</em>
          </button>
        ))
      )}
    </div>
  );
}

function DataPanel({
  snapshot,
  run,
}: {
  snapshot: Snapshot;
  run: (action: string, input: Record<string, unknown>, done: string) => void;
}) {
  const budget = snapshot.budget ?? {};
  const [limit, setLimit] = useState(String(budget.limit_units ?? ""));
  const archived = (snapshot.objects?.task ?? []).filter((item) => text(item, "status") === "archived");
  return (
    <div className={styles.panelList}>
      <p className={styles.confirmNote}>
        模型：{snapshot.provider?.configured ? snapshot.provider.model || "已配置" : "没配"}
        {" · "}判定：{snapshot.provider?.judge || "规则"}
        {" · "}Jev：{snapshot.provider?.jev || "没配"}
        <br />
        额度是「本地调用配额」，不是人民币：上限 {budget.limit_units ?? "-"} · 已用 {budget.spent ?? "-"} ·
        预留 {budget.reserved ?? "-"}。
      </p>
      <label className={styles.panelField}>
        <span>本地额度上限</span>
        <input value={limit} inputMode="numeric" onChange={(event) => setLimit(event.target.value)} />
      </label>
      <button
        type="button"
        className={styles.panelAction}
        disabled={!limit.trim() || Number.isNaN(Number(limit))}
        onClick={() => run("budget.set", { limit_units: Number(limit) }, "额度上限已保存")}
      >
        保存额度上限
      </button>
      <a className={styles.panelAction} href="/api/elfred/export" download="elfred-export.json">
        导出我的数据（原始 JSON）
        <ChevronRight size={16} />
      </a>
      <h3 className={styles.panelTitle}>已归档任务（{archived.length}）</h3>
      {archived.length === 0 ? (
        <p className={styles.confirmNote}>没有归档的任务。</p>
      ) : (
        archived.map((item) => (
          <button
            type="button"
            key={item.id}
            className={styles.panelAction}
            onClick={() => run("task.restore", ref(item), "任务已恢复")}
          >
            {displayTitle(text(item, "title"),'') || "（没写标题的任务）"}
            <em>恢复</em>
          </button>
        ))
      )}
    </div>
  );
}
