// 主页聚合模块：第四页那几个"数"都从这里出，服务端算、前端只读。
//
// 为什么单开一个模块：这些数以前一半在前端（勋章）、一半塞在 service.mjs 里（关注/粉丝/获赞），
// 同一类东西两套算法、两处审计。现在收到一起：
//
//   social.mjs  关注 / 粉丝 / 获赞（别人对我的动作，只有服务端看得全）
//   badges.mjs  勋章（第二页「理解度 → 荣誉勋章」和第四页「勋章」共用同一份）
//
// 出口只有一个：`profileStats(store, user)` —— 结果被拼进 /bootstrap 的快照。
import { socialCounts } from './social.mjs';
import { badgeList } from './badges.mjs';

export function profileStats(store, user) {
  // 勋章只把清单拼进快照（前端要的就是一张表）；条数/最高等级这类统计留给需要的一方自己算，
  // 免得同一组数在快照里出现两份。
  return { social: socialCounts(store, user), badges: badgeList(store, user).badges };
}
