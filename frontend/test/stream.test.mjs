import test from 'node:test';
import assert from 'node:assert/strict';
import { readEvents } from '../public/sse.js';
import { receive, finish, decisionFor } from '../public/state.js';

test('parses split UTF8, CRLF, comments, multiline data and multiple frames', async () => {
  const bytes = new TextEncoder().encode(': heartbeat\r\n\r\nevent: token\r\ndata: {"content":\r\ndata: "中文"}\r\n\r\nevent: done\ndata: {"status":"completed"}\n\n');
  const stream = new ReadableStream({ start(c) { for (const byte of bytes) c.enqueue(new Uint8Array([byte])); c.close(); } });
  const events = []; await readEvents(stream, (name, data) => events.push([name, data]));
  assert.deepEqual(events, [['token', { content: '中文' }], ['done', { status: 'completed' }]]);
});
test('final result replaces streamed text, completion requires a business result', () => {
  const m = { text: '' }; receive(m, 'token', { content: '部分' }); receive(m, 'result', { answer: '完整', sources: [] }); receive(m, 'done', {}); finish(m);
  assert.equal(m.text, '完整'); assert.equal(m.done, true); assert.equal(m.error, undefined);
  assert.throws(() => receive({ text: '' }, 'done', {}));
});
test('HTTP success and partial tokens are not success if stream is truncated', () => {
  const m = { text: '' }; receive(m, 'token', { content: '退款' }); finish(m);
  assert.ok(m.error); assert.notEqual(m.done, true);
});
test('approval stays pending after done and error cannot become success', () => {
  const m = { text: '' }; receive(m, 'approval_required', { approval: { order_id: 'A1001' } }); receive(m, 'done', {});
  assert.equal(m.approval.order_id, 'A1001'); assert.equal(m.resolved, undefined);
  const failed = { text: '' }; receive(failed, 'error', { message: '失败' }); receive(failed, 'done', {}); assert.equal(failed.done, undefined);
});
test('approval retry persists original key and cannot change decision', () => {
  const m = {}; const d = decisionFor(m, true, () => 'stable-key');
  const restored = JSON.parse(JSON.stringify(m));
  assert.deepEqual(decisionFor(restored, true, () => 'new-key'), d);
  assert.throws(() => decisionFor(restored, false, () => 'another-key'));
});
