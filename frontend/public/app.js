import { readEvents } from './sse.js';
import { receive, finish, decisionFor } from './state.js';

const $ = s => document.querySelector(s);
let storageKey, accessToken = sessionStorage.getItem('support-access-token'), currentUser;
const intents = { order_query: '订单查询', policy_query: '政策问答', refund: '退款申请', complaint: '投诉建议', other: '一般咨询' };
const statuses = { PAID: '已支付', SHIPPED: '已发货', COMPLETED: '已完成', PENDING_PAYMENT: '待支付', REFUNDING: '退款处理中', REFUNDED: '已退款', CANCELLED: '已取消' };
let sessions = [], currentId, busy = false, healthTimer, trace = [];
function showLogin(message = '') {
  clearTimeout(healthTimer); accessToken = null; currentUser = null; sessionStorage.removeItem('support-access-token');
  sessions = []; currentId = undefined; storageKey = undefined; trace = [];
  $('#messages').replaceChildren(); $('#sessions').replaceChildren(); $('#input').value = '';
  $('#workspace').hidden = true; $('#login-screen').hidden = false;
  $('#login-error').textContent = message; $('#login-error').hidden = !message;
  $('#password').value = '';
}
async function openWorkspace(user) {
  currentUser = user; storageKey = `support-auth-v1:${user.tenantId}:${user.userId}`;
  sessions = [];
  try { const parsed = JSON.parse(localStorage.getItem(storageKey) || '[]'); if (Array.isArray(parsed)) sessions = parsed.filter(s => s.id && Array.isArray(s.messages)).slice(0, 20); } catch {}
  for (const s of sessions) for (const m of s.messages) { if (m.role === 'assistant' && !m.done && !m.error) finish(m); }
  currentId = sessions[0]?.id;
  $('#profile-name').replaceChildren(document.createTextNode(user.username), el('small', '', `${user.tenantId} · ${user.userId}`));
  $('#identity-caption').textContent = `已认证：${user.username} · ${user.role}`;
  $('#order-id').value = user.userId === 'U2002' ? 'B2001' : 'A1001';
  $('#login-screen').hidden = true; $('#workspace').hidden = false;
  if (!currentId) newSession(); else render();
  checkHealth(); loadOrder();
}
function active() { return sessions.find(s => s.id === currentId); }
function save() { if (!storageKey) return; try { localStorage.setItem(storageKey, JSON.stringify(sessions)); } catch { notice('浏览器存储不可用，本次记录仅保留在当前页面。'); } }
function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }
function answerText(text) {
  const n = el('div', text ? 'message-text' : 'pending');
  if (!text) { n.textContent = '正在理解你的问题…'; return n; }
  // Format emphasis without interpreting model output as HTML or executable links.
  for (const part of text.split(/(\*\*[^*]+\*\*)/g)) n.append(part.startsWith('**') && part.endsWith('**') ? el('strong', '', part.slice(2, -2)) : document.createTextNode(part));
  return n;
}
function notice(text = '') { $('#notice').textContent = text; $('#notice').hidden = !text; }
function newSession() {
  if (busy || !currentUser) return;
  const existing = sessions.find(s => !s.messages.length);
  if (existing) currentId = existing.id;
  else { const s = { id: crypto.randomUUID(), title: '新的会话', messages: [], date: new Date().toISOString() }; sessions.unshift(s); sessions = sessions.slice(0, 20); currentId = s.id; }
  trace = []; save(); render(); renderTrace(); notice(); $('#input').focus();
}
function renderSessions() {
  $('#sessions').replaceChildren(); $('#session-count').textContent = sessions.length;
  for (const s of sessions) {
    const button = el('button', `session${s.id === currentId ? ' active' : ''}`); button.disabled = busy;
    button.append(el('span', '', '◷')); const label = el('span', 'session-text', s.title);
    label.append(el('small', '', new Date(s.date).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }))); button.append(label);
    button.title = s.title; button.setAttribute('aria-label', s.title); button.onclick = () => { currentId = s.id; trace = []; notice(); render(); renderTrace(); };
    $('#sessions').append(button);
  }
}
function pendingApproval(s = active()) { return s?.messages.find(m => m.approval && !m.resolved); }
function controls() {
  const pending = pendingApproval();
  $('#send').disabled = busy || !!pending; $('#new-chat').disabled = busy;
  $('#logout').disabled = busy;
  $('#input').disabled = busy || !!pending;
  $('#session-state').textContent = busy ? '正在处理…' : pending ? '等待退款确认' : '准备就绪';
  $('#thread-id').textContent = active()?.threadId || '发送首条消息后创建';
  document.querySelectorAll('[data-prompt]').forEach(b => b.disabled = busy || !!pending);
  if (pending && !busy) notice('当前会话有待确认的退款，请先处理确认卡片。也可以新建会话查询订单。');
}
function render() {
  renderSessions(); const s = active(); const area = $('#scroll-area'); const wasBottom = area.scrollHeight - area.scrollTop - area.clientHeight < 100;
  $('#welcome').hidden = !!s?.messages.length; $('#messages').replaceChildren();
  for (const m of s?.messages || []) {
    const row = el('article', `message ${m.role}`);
    if (m.role === 'assistant') row.append(el('span', 'assistant-icon', '✧'));
    const bubble = el('div', 'bubble'); bubble.append(el('div', 'message-label', m.result ? `服务助手 · ${intents[m.result.intent] || m.result.intent}` : '服务助手'));
    bubble.append(answerText(m.text));
    if (m.result?.sources?.length) {
      const list = el('div', 'sources'); for (const source of m.result.sources) list.append(el('span', 'source', `[${source.reference_number}] ${source.title}${source.section_title ? ' · ' + source.section_title : ''} · ${source.version}`)); bubble.append(list);
    }
    if (m.approval && !m.resolved) {
      const a = m.approval, card = el('div', 'approval'); card.append(el('h3', '', '◇ 退款申请 · 等待你的确认'), el('p', '', `${a.order_id} · ${a.product_name}`), el('p', '', `订单金额 ¥${Number(a.total_amount).toFixed(2)} · ${statuses[a.status] || a.status}`), el('p', '', '确认后提交退款申请；受理不代表资金已经退回。'));
      if (m.decision) card.append(el('p', '', '上次提交结果未确认。重试会沿用同一个幂等键和决定。'));
      const actions = el('div', 'approval-actions');
      for (const approved of [false, true]) {
        const button = el('button', approved ? 'primary' : '', m.decision?.approved === approved ? '重试原决定' : approved ? '确认申请退款' : '取消退款');
        button.disabled = busy || (!!m.decision && m.decision.approved !== approved);
        button.onclick = () => resume(m, approved); actions.append(button);
      }
      card.append(actions); bubble.append(card);
    }
    if (m.error) bubble.append(el('div', 'error', m.error));
    row.append(bubble); $('#messages').append(row);
  }
  controls(); if (wasBottom || busy) area.scrollTop = area.scrollHeight;
}
function addTrace(title, detail) { trace.push({ title, detail, time: new Date().toLocaleTimeString('zh-CN', { hour12: false }) }); renderTrace(); }
function renderTrace() {
  $('#trace').replaceChildren();
  if (!trace.length) $('#trace').append(el('li', '', '发送消息后展示实际收到的事件'));
  for (const entry of trace) { const li = el('li', '', entry.title); li.append(el('small', '', `${entry.time}${entry.detail ? ' · ' + entry.detail : ''}`)); $('#trace').append(li); }
}
async function api(path, options = {}) {
  const r = await fetch(path, { ...options, signal: options.signal || AbortSignal.timeout(120000), headers: { 'Content-Type': 'application/json', ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}), ...options.headers } });
  if (!r.ok) { let message = `请求失败（HTTP ${r.status}）`; try { const b = await r.json(); message = b.message || b.detail || message; } catch {} if (r.status === 401) showLogin(message); throw new Error(message); } return r;
}
async function threadLock(s, action) {
  if (!navigator.locks) throw new Error('请使用新版 Chrome 或 Edge 以保证会话操作顺序。');
  return navigator.locks.request(`support-demo:${s.id}`, { ifAvailable: true }, async lock => {
    if (!lock) throw new Error('另一个标签页正在处理该会话，请稍后再试。');
    // A tab may have stale state even after the other tab releases its lock.
    const stored = JSON.parse(localStorage.getItem(storageKey) || '[]').find(x => x.id === s.id);
    if (stored && JSON.stringify(stored) !== JSON.stringify(s)) throw new Error('会话已在另一标签页更新，请刷新页面后继续。');
    return action();
  });
}
async function send(text) {
  if (busy || !currentUser || pendingApproval() || !text.trim()) return;
  if (!active()) newSession();
  const s = active(); busy = true; notice(); trace = []; $('#elapsed').textContent = '处理中'; const start = performance.now();
  let message;
  try {
    await threadLock(s, async () => {
      s.messages.push({ role: 'user', text: text.trim() });
      if (s.messages.length === 1) s.title = text.trim().slice(0, 24);
      message = { role: 'assistant', text: '' }; s.messages.push(message); save(); $('#input').value = ''; $('#counter').textContent = '0 / 4000'; render();
      if (!s.threadId) {
        const created = await (await api('/api/v1/agent/threads', { method: 'POST' })).json();
        s.threadId = created.thread_id; save(); addTrace('会话已创建', s.threadId.slice(0, 8));
      }
      addTrace('请求已发送', '等待服务端事件');
      const response = await api('/api/v1/agent/chat/stream', { method: 'POST', headers: { Accept: 'text/event-stream' }, body: JSON.stringify({ thread_id: s.threadId, message: text.trim() }) });
      if (!response.headers.get('content-type')?.includes('text/event-stream')) throw new Error('服务未返回 SSE 事件流');
      let firstToken = true;
      await readEvents(response.body, (event, data) => {
        receive(message, event, data);
        if (event === 'metadata') addTrace('流式连接已建立', 'metadata');
        if (event === 'token' && firstToken) { firstToken = false; addTrace('开始接收回答', `${((performance.now() - start) / 1000).toFixed(1)}s 首段延迟`); }
        if (event === 'result') addTrace('收到业务结果', intents[data.intent] || data.intent);
        if (event === 'approval_required') { addTrace('工作流等待确认', data.order_id); save(); }
        if (event === 'error') addTrace('服务返回错误', data.code);
        if (event === 'done') addTrace(message.approval ? '本轮结束，等待人工确认' : '本轮已完成', 'done');
        render();
      });
      finish(message);
      if (message.result?.order_id || message.approval?.order_id) { $('#order-id').value = message.result?.order_id || message.approval.order_id; await loadOrder(); }
    });
  } catch (error) { if (message) message.error = error.message; else notice(error.message); addTrace('请求未完成', '未自动重试'); }
  finally { busy = false; $('#elapsed').textContent = `${((performance.now() - start) / 1000).toFixed(1)}s`; if (message) save(); render(); }
}
async function resume(message, approved) {
  if (busy) return;
  const s = active(); busy = true; notice(); let submitted = false;
  try {
    await threadLock(s, async () => {
      const decision = decisionFor(message, approved, () => crypto.randomUUID());
      submitted = true;
      save(); render(); addTrace(approved ? '提交退款确认' : '提交取消决定', '使用固定幂等键');
      const result = await (await api(`/api/v1/agent/threads/${encodeURIComponent(s.threadId)}/resume`, { method: 'POST', headers: { 'Idempotency-Key': decision.key }, body: JSON.stringify({ approved }) })).json();
      message.resolved = true; message.done = true; delete message.error;
      s.messages.push({ role: 'assistant', text: result.answer, result, done: true });
      addTrace('收到恢复执行结果', intents[result.intent] || result.intent);
      $('#order-id').value = message.approval.order_id; await loadOrder(); save();
    });
  } catch (error) { if (submitted) message.error = `${error.message} 请核实订单状态；原决定和幂等键已保留。`; else notice(error.message); addTrace('恢复请求未确认', '未标记退款成功'); }
  finally { busy = false; if (submitted) save(); render(); }
}
async function loadOrder() {
  const id = $('#order-id').value.trim(); if (!/^[\w-]{1,64}$/.test(id)) { $('#order-card').replaceChildren(el('p', 'error', '请输入有效订单号')); return; }
  $('#order-card').replaceChildren(el('p', 'caption', '正在查询业务系统…'));
  try {
    const o = await (await api(`/api/v1/orders/${encodeURIComponent(id)}`, { signal: AbortSignal.timeout(10000) })).json();
    const box = $('#order-card'); box.replaceChildren(); const top = el('div', 'order-top'); top.append(el('span', '', o.orderId), el('span', '', statuses[o.status] || o.status)); box.append(top, el('h3', '', o.productName), el('div', 'price', `¥ ${Number(o.totalAmount).toFixed(2)}`));
    const dl = el('dl'); for (const [k, v] of [['商品数量', `${o.quantity} 件`], ['退款资格', o.refundable ? '可申请' : '当前不可申请']]) dl.append(el('dt', '', k), el('dd', '', v)); box.append(dl);
  } catch (error) { $('#order-card').replaceChildren(el('p', 'error', error.message)); }
}
async function checkHealth() {
  clearTimeout(healthTimer);
  if (!currentUser) return;
  const [java, agent] = await Promise.allSettled([
    api('/api/v1/system/info', { signal: AbortSignal.timeout(5000) }).then(r => r.json()),
    api('/api/agent-health', { signal: AbortSignal.timeout(5000) }).then(r => r.json())
  ]);
  const j = java.status === 'fulfilled', p = agent.status === 'fulfilled';
  const rag = p ? agent.value.components?.rag?.status : 'UNKNOWN';
  const redis = p ? agent.value.components?.redis?.status : 'UNKNOWN';
  $('#connection').textContent = j && p ? (rag === 'UP' ? '服务已连接' : '已连接 · 知识库受限') : '部分服务未连接';
  $('#services').replaceChildren();
  for (const [title, value, up] of [['业务服务', j ? '已连接' : '未连接', j], ['Agent 服务', p ? '已连接' : '未连接', p], ['知识检索', rag === 'UP' ? '可用' : '未就绪', rag === 'UP'], ['Agent 缓存', redis === 'UP' ? '可用' : '未启用 / 不可用', redis === 'UP']]) {
    const row = el('div', 'service-row'); row.append(el('span', '', title), el('span', `service-value${up ? '' : ' warn'}`, value)); $('#services').append(row);
  }
  if (currentUser) healthTimer = setTimeout(checkHealth, 30000);
}
$('#new-chat').onclick = newSession;
document.addEventListener('keydown', e => { if (e.key.toLowerCase() === 'n' && !e.ctrlKey && !e.altKey && !e.metaKey && !['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) { e.preventDefault(); newSession(); } });
$('#composer').onsubmit = e => { e.preventDefault(); send($('#input').value); };
$('#input').oninput = () => $('#counter').textContent = `${$('#input').value.length} / 4000`;
$('#input').onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send($('#input').value); } };
document.querySelectorAll('[data-prompt]').forEach(button => button.onclick = () => {
  const orderId = $('#order-id').value.trim();
  if (button.dataset.prompt.includes('{order_id}') && !/^[\w-]{1,64}$/.test(orderId)) {
    notice('请先在订单速览中填写有效订单号。'); return;
  }
  send(button.dataset.prompt.replace('{order_id}', orderId));
});
$('#order-form').onsubmit = e => { e.preventDefault(); loadOrder(); };
$('#health-refresh').onclick = checkHealth; $('#refresh-side').onclick = checkHealth;
window.addEventListener('storage', e => { if (e.key === storageKey && !busy) { try { sessions = JSON.parse(e.newValue || '[]'); if (!active()) currentId = sessions[0]?.id; render(); } catch {} } });
$('#login-form').onsubmit = async e => {
  e.preventDefault(); $('#login-submit').disabled = true; $('#login-error').hidden = true;
  try {
    const r = await fetch('/api/v1/auth/login', { method: 'POST', signal: AbortSignal.timeout(15000), headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: $('#username').value.trim(), password: $('#password').value }) });
    const data = await r.json(); if (!r.ok) throw new Error(data.message || '登录失败');
    accessToken = data.access_token; sessionStorage.setItem('support-access-token', accessToken); $('#password').value = '';
    await openWorkspace(await (await api('/api/v1/auth/me')).json());
  } catch (error) { showLogin(error.message); }
  finally { $('#login-submit').disabled = false; }
};
$('#logout').onclick = async () => {
  if (busy) return; $('#logout').disabled = true;
  try { await api('/api/v1/auth/logout', { method: 'POST' }); showLogin('已安全退出，原登录凭证已失效。'); }
  catch (error) { if (currentUser) notice(`退出尚未完成：${error.message}。请重试，不能只清除浏览器凭证。`); }
  finally { $('#logout').disabled = false; }
};
if (accessToken) {
  try { await openWorkspace(await (await api('/api/v1/auth/me')).json()); }
  catch (error) { showLogin(error.message); }
} else showLogin();
