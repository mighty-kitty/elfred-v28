/**
 * 主页上的三个数：关注 / 粉丝 / 获赞。
 *   · 粉丝和获赞是"别人对我"的动作，前端只看得到自己的互动记录，所以聚合放服务端算；
 *   · 全部来自真实对象：`interaction`（关注 / 点赞，`active` 才算数）+ 帖子自带的计数；
 *   · 没有就是 0，不编数。
 */
export function socialCounts(store, user) {
  const interactions = store.list('interaction');
  const on = (item) => item.data?.active === true;
  const following = new Set(interactions
    .filter((item) => item.owner === user && item.data.kind === 'follow_author' && on(item))
    .map((item) => item.data.object_id)).size;
  const followers = new Set(interactions
    .filter((item) => item.owner !== user && item.data.kind === 'follow_author' && on(item) && item.data.object_id === user)
    .map((item) => item.owner)).size;
  const posts = store.list('post').filter((item) => item.owner === user);
  const ids = new Set(posts.map((item) => item.id));
  const stored = posts.reduce((total, item) => total + Number(item.data.likes || 0), 0);
  const liked = new Set(interactions
    .filter((item) => item.owner !== user && item.data.kind === 'like' && on(item) && ids.has(item.data.object_id))
    .map((item) => `${item.owner}:${item.data.object_id}`)).size;
  return { following, followers, likes: stored + liked };
}
