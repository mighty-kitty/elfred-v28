import {test} from 'node:test';
import assert from 'node:assert/strict';
import {indexPrivateFeed} from '../../app/v28/features/home/feed-ranking.mjs';

const today = '2026-09-27';
function fixture(count = 100) {
  const feed = Array.from({length: count}, (_, i) => ({id: 'feed-' + i, created: new Date(Date.UTC(2026, 8, 27) - i * 3600000).toISOString(), data: {
    topic: ['旧话题', '设计', '工程', '静音话题'][i % 4], system: ['explore', 'create', 'execute'][i % 3],
    task_id: i % 7 === 0 ? 'today' : 'past', artifact_id: i % 11 === 0 ? 'result' : null,
  }}));
  return {server_time: '2026-09-27T08:00:00Z', objects: {feed,
    settings: [{data: {feed_topics: {'旧话题': {alias: '设计'}, '设计': {mode: 'follow'}, '静音话题': {mode: 'mute', removed: true}}}}],
    task: [{id: 'today', data: {focus_date: today}}, {id: 'past', data: {focus_date: '2026-09-26'}}],
    interaction: [{data: {object_id: 'feed-0', kind: 'like', active: true}}, {data: {object_id: 'feed-0', kind: 'hide', active: true}},
      {data: {object_id: 'feed-2', kind: 'less', active: true}}, {data: {object_id: 'feed-1', kind: 'like', active: false}}],
  }};
}
test('index preserves recommendation rules for aliases, hidden likes, same-agent reductions, task focus and topic preferences', () => {
  const snapshot = fixture();
  const active = (id, kind) => snapshot.objects.interaction.some(i => i.data.object_id === id && i.data.kind === kind && i.data.active);
  const settings = snapshot.objects.settings[0].data.feed_topics;
  const topic = item => settings[item.data.topic]?.alias || item.data.topic;
  const score = item => {
    const likes = snapshot.objects.feed.filter(candidate => topic(candidate) === topic(item) && active(candidate.id, 'like')).length;
    const less = snapshot.objects.feed.some(candidate => topic(candidate) === topic(item) && candidate.data.system === item.data.system && active(candidate.id, 'less'));
    return (snapshot.objects.task.find(task => task.id === item.data.task_id)?.data.focus_date === today ? 3 : 0)
      + (item.data.artifact_id ? 2 : 0) + Math.min(likes, 2) - (Date.parse(snapshot.server_time) - Date.parse(item.created)) / 86400000 / 7
      - (less ? 8 : 0) + (settings[topic(item)]?.mode === 'follow' ? 3 : 0) - (settings[topic(item)]?.mode === 'mute' ? 20 : 0);
  };
  const index = indexPrivateFeed(snapshot, today);
  assert.deepEqual(index.recommended.map(i => i.id), snapshot.objects.feed.slice().sort((a, b) => score(b) - score(a) || b.created.localeCompare(a.created)).map(i => i.id));
  assert.deepEqual(index.latest.map(i => i.id), snapshot.objects.feed.map(i => i.id));
  assert.deepEqual(index.topicOptions, ['设计', '工程']);
  assert.equal(index.isActive('feed-0', 'hide'), true);
  assert.equal(index.isActive('feed-1', 'like'), false);
  assert.equal(index.topics.get('feed-0'), '设计');
});
test('a large feed remains interactive without rescanning all entries per sort comparison', () => {
  const snapshot = fixture(10000), start = performance.now();
  const index = indexPrivateFeed(snapshot, today);
  assert.equal(index.recommended.length, 10000);
  assert.ok(performance.now() - start < 2000, '10,000 entries should rank within two seconds even on slower CI');
  assert.equal(snapshot.objects.feed[0].id, 'feed-0', 'ranking must not mutate snapshot order');
});
