/**
 * 能力卡初始化模块：把"新用户选的几个选项"变成**真正能用的能力卡**。
 *
 * 为什么单开一个模块（而不是塞进工具库）：它跨三样东西——工具库（落 skill）、任务（配草稿）、
 * 记忆（把偏好记下来），而且要有自己的一笔"这次初始化选了什么"的记录。工具库只管工具版本，
 * 不该知道"用户是怎么被引导来的"。
 *
 * 一张卡生成时写齐三样，保证三处界面同源：
 *   ① skill.instructions  说明书（四小节，卡片详情按它渲染"能做到什么 / 步骤 / 交付"）
 *   ② skill.parameters    这次要喂什么（点"用它做一件事"时会问）
 *   ③ skill.workflow      需要别的系统先做的前置步骤（决定任务预算与协作步骤）
 * 并顺手配一条**任务草稿**（不自动跑，维持"确认后才运行"）。
 *
 * 铁律：初始化只给"起点卡"——等级/分数仍只由验收过的成果推；重复选同一张卡不会生成第二张；
 * 有东西没写成（比如记忆），如实记在回执里，不假装全成。
 */
import { fail, now } from '../store.mjs';
import { toolLibraryCommand } from '../tool-library.mjs';
import { taskCommand } from '../runtime.mjs';
import { knowledgeCommand } from '../knowledge.mjs';
import {
  composeSkillMarkdown, composeTaskDraft, composeToolParameters, composeToolWorkflow,
  customPreset, normalizePreferences, presetById, presetIdFromText, resolvePath,
  validateSelection, PREFERENCE_GROUPS, SYSTEMS,
} from '../../../app/v28/core/card-onboarding.mjs';

export const RECORD_TYPE = 'card_onboarding';

const knownPresetIds = (store, user) => new Set(
  store.list('skill')
    .filter((item) => item.owner === user && item.data.onboarding?.preset_id)
    .map((item) => item.data.onboarding.preset_id),
);

/** 只把**没选默认值**的那几项记成记忆：默认值不是用户表达的偏好，记下来就是噪音 */
function preferencesWorthRemembering(preferences) {
  const normalized = normalizePreferences(preferences);
  return PREFERENCE_GROUPS
    .filter((group) => normalized[group.id] !== group.defaultValue)
    .map((group) => {
      const option = group.options.find((item) => item.value === normalized[group.id]);
      return `${group.label}：${option?.label || normalized[group.id]}`;
    });
}

/**
 * 把这次的选择解成"要生成哪些卡 + 每张卡带哪些内容片段"。三条入口：
 *   ① path[]       —— 分支选择树（新流程）：路径决定是哪张卡，也决定说明书里写什么；
 *   ② custom_text  —— "都不太对，我自己说一句"：先按关键词落到某张现成卡，落不到才造一张"其它"卡；
 *   ③ preset_ids[] —— 老入口（"再来一张"、脚本与测试仍在用），等价于"选定了卡、不带片段"。
 */
function resolvePicks(input) {
  const customText = String(input?.custom_text || '').trim().slice(0, 200);
  const customSystem = SYSTEMS.includes(input?.custom_system) ? input.custom_system : null;
  if (Array.isArray(input?.path) && input.path.length) {
    const resolved = resolvePath(input.path);
    if (!resolved.ok) return { ok: false, reason: resolved.reason };
    return {
      ok: true,
      picks: [{ preset: resolved.preset, fragments: resolved.fragments, custom: false }],
      trail: resolved.trail,
      fragmentIds: resolved.fragmentIds,
      customText, customSystem,
    };
  }
  if (customText || customSystem) {
    const hit = customText ? presetIdFromText(customText) : null;
    const matched = hit ? presetById(hit) : null;
    // 用户自己指定过归属就以他为准（界面里"归哪一类"是可改的，默认显示系统推断的那一维）
    const preset = matched
      ? { ...matched, system: customSystem || matched.system }
      : customPreset(customText, customSystem);
    // 落到现成卡时，把本人那句话也写进说明书；"其它"卡的 canDo 本身就是那句话，不用再重复
    const fragments = hit && customText ? [{ id: 'custom-say', notes: [`本人原话：${customText}`] }] : [];
    return { ok: true, picks: [{ preset, fragments, custom: !hit }], trail: [], fragmentIds: [], customText, customSystem };
  }
  const selection = validateSelection(input || {});
  if (!selection.ok) return { ok: false, reason: selection.reason };
  return {
    ok: true,
    picks: selection.presets.map((preset) => ({ preset, fragments: [], custom: preset.id === 'custom' })),
    trail: [], fragmentIds: [], customText: selection.customText, customSystem: selection.customSystem,
  };
}

/**
 * 命令 `card.onboard`：登记**并立刻生成**（这里是纯对象写入，不发网络请求，所以不需要走 tick）。
 * input: { path?: string[], preset_ids?: string[], custom_text?: string, custom_system?: string, preferences?: {} }
 */
export function cardOnboardCommand(store, user, action, input) {
  if (action !== 'card.onboard') return null;
  const resolved = resolvePicks(input || {});
  if (!resolved.ok) fail('INVALID_INPUT', resolved.reason);
  const { picks, trail, fragmentIds, customText, customSystem } = resolved;
  const preferences = normalizePreferences(input?.preferences || {});
  const already = knownPresetIds(store, user);
  const notes = [];
  const created = [];
  const skipped = [];

  for (const pick of picks) {
    const { preset, fragments } = pick;
    if (preset.id !== 'custom' && already.has(preset.id)) {
      skipped.push({ preset_id: preset.id, title: preset.title, reason: '这张卡你已经有了' });
      continue;
    }
    const markdown = composeSkillMarkdown(preset, { fragments, preferences });
    const saved = toolLibraryCommand(store, user, 'tool.save', {
      title: preset.title,
      instructions: markdown,
      kind: 'Skill',
      system: preset.system,
      parameters: composeToolParameters(preset, { fragments }),
      workflow: composeToolWorkflow(preset),
    });
    toolLibraryCommand(store, user, 'tool.activate', { id: saved.id, version: saved.version });
    const skill = store.get(saved.id);
    const version = store.get(skill.data.version_id);
    store.update(skill, {
      ...skill.data,
      // 来源标出来：以后能区分"初始化卡 / Foundry 起草 / 手建"，也用于去重
      source: 'onboarding',
      onboarding: {
        preset_id: preset.id, system: preset.system, preferences,
        path: trail.map((item) => item.id), fragments: fragmentIds, at: now(),
      },
    }, user);

    // 立刻配一条草稿：绑定这张卡的版本，并把路径片段与偏好作为约束带进去
    const draft = composeTaskDraft(preset, { fragments, preferences });
    const task = taskCommand(store, user, 'task.create', {
      goal: draft.goal,
      criteria: draft.criteria,
      constraints: draft.constraints,
      mode: 'compose',
      system: preset.system,
      source_refs: [{ id: version.id, version: version.version }],
    });
    const created_task = store.get(task.id);
    const linked = store.update(created_task, {
      ...created_task.data,
      skill_id: skill.id,
      skill_version_id: version.id,
      parameter_values: {},
      onboarding: { preset_id: preset.id, at: now() },
    }, user);
    created.push({
      preset_id: preset.id,
      title: preset.title,
      system: preset.system,
      skill_id: skill.id,
      skill_version_id: version.id,
      task_id: linked.id,
    });
  }

  // 偏好里"不是默认值"的那几条记成记忆（低风险自动学，来源指向这次初始化）
  const memoryNotes = preferencesWorthRemembering(preferences);
  const record = store.add(RECORD_TYPE, user, {
    status: 'completed',
    preset_ids: picks.filter((pick) => pick.preset.id !== 'custom').map((pick) => pick.preset.id),
    custom_text: customText || null,
    custom_system: customSystem || null,
    path: trail.map((item) => item.id),
    path_labels: trail.map((item) => `${item.question}→${item.label}`),
    fragment_ids: fragmentIds,
    preferences,
    created: created.map((item) => ({ preset_id: item.preset_id, skill_id: item.skill_id, task_id: item.task_id })),
    skipped,
    at: now(),
  });
  for (const note of memoryNotes) {
    try {
      knowledgeCommand(store, user, 'memory.create', {
        content: `用户希望：${note}`,
        scope: 'owner',
        risk: 'low',
        source_refs: [{ id: record.id, version: record.version }],
        purpose: '来自首次能力卡初始化时本人选择的偏好，用于后续同类任务',
      });
    } catch (error) {
      // 记忆写失败不影响卡与任务；如实记在回执里
      notes.push(`有一条偏好没能记成理解：${error instanceof Error ? error.message : '未知原因'}`);
    }
  }

  return {
    id: record.id,
    created,
    skipped,
    preferences,
    remembered: memoryNotes,
    notes,
  };
}
