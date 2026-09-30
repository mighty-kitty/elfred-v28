// 轻量测试（那份 22 题的短问卷）的服务端半边：校验作答、算起点、落库。
// 打分是纯函数，和前端共用 app/v28/core/dimensions.mjs —— 这里只负责"存哪、怎么覆盖"。
//
// 为什么用对象表而不是新建关系表：这两页的其它状态（profile / settings / onboarding）
// 都走现成的对象 + 命令机制，没有迁移框架；加一张表要改 user_version 和一处 schema，
// 单独为一份问卷引入迁移不划算。
import { fail, now } from '../store.mjs';
import { QUESTIONNAIRE_ITEMS, QUESTIONNAIRE_VERSION, questionnairePaper, scoreQuestionnaire } from '../../../app/v28/core/dimensions.mjs';

export const BASELINE_TYPE = 'dimension_baseline';

function rows(store, user) {
  return store.visible(user, BASELINE_TYPE).filter((item) => item.owner === user && item.data.status !== 'archived');
}

/** 当前生效的那份起点（没有就是 null，界面据此走"还没测过"的空态）。 */
export function questionnaireBaseline(store, user) {
  const row = rows(store, user)[0];
  if (!row) return null;
  return {
    axes: row.data.axes ?? {},
    guard: Number(row.data.guard || 0),
    version: Number(row.data.questionnaire_version || QUESTIONNAIRE_VERSION),
    takenAt: row.data.taken_at,
  };
}

/** GET 那份测试要的东西：题目 + 这个账号测过没有。 */
export function questionnaireView(store, user) {
  const baseline = questionnaireBaseline(store, user);
  return { ...questionnairePaper(), taken: Boolean(baseline), baseline };
}

function cleanAnswers(answers) {
  const known = new Map(QUESTIONNAIRE_ITEMS.map((item) => [item.id, item.options.length]));
  const picked = [];
  for (const row of Array.isArray(answers) ? answers : []) {
    if (!row || typeof row !== 'object') continue;
    const id = String(row.id ?? '');
    const choice = Number(row.choice);
    const options = known.get(id);
    if (!options || !Number.isInteger(choice) || choice < 0 || choice >= options) continue;
    picked.push({ id, choice });
  }
  if (new Set(picked.map((row) => row.id)).size < QUESTIONNAIRE_ITEMS.length) {
    fail('INVALID_INPUT', `请把 ${QUESTIONNAIRE_ITEMS.length} 题都答完再提交`);
  }
  return picked;
}

export function questionnaireCommand(store, user, action, input) {
  if (action !== 'questionnaire.submit') return null;
  const answers = cleanAnswers(input.answers);
  const scored = scoreQuestionnaire(answers);
  if (!Object.keys(scored.axes).length) fail('INVALID_INPUT', '这份作答里没有可用的答案，请重新答一遍');
  const data = {
    questionnaire_version: QUESTIONNAIRE_VERSION,
    axes: scored.axes,
    guard: scored.guard,
    answers,
    taken_at: now(),
    status: 'active',
  };
  // 重测 = 覆盖同一份起点（版本号跟着走），不做"一人多份起点"——起点只有一份才有意义。
  const existing = rows(store, user)[0];
  const saved = existing ? store.update(existing, data, user) : store.add(BASELINE_TYPE, user, data);
  return { ok: true, id: saved.id, version: saved.version, axes: scored.axes, guard: scored.guard, taken_at: data.taken_at };
}
