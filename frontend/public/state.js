export function receive(message, event, data) {
  if (message.done || message.error) return;
  switch (event) {
    case 'token': message.text += data.content || ''; break;
    case 'result':
      message.text = data.answer || ''; message.result = data; message.outcome = 'result'; break;
    case 'approval_required':
      message.approval = data.approval; message.outcome = 'approval';
      message.text = '已核对订单信息。请确认是否提交退款申请。'; break;
    case 'done':
      if (!message.outcome) throw new Error('服务结束但未返回业务结果');
      message.done = true; break;
    case 'error': message.error = data.message || '处理失败'; break;
  }
}
export function finish(message) {
  if (!message.done && !message.error) message.error = '连接已中断，结果未确认。请先查询订单状态，不会自动重新提交。';
}
export function decisionFor(message, approved, newKey) {
  if (message.decision && message.decision.approved !== approved) throw new Error('上次请求结果尚未确认，请使用原决定重试或先核实订单。');
  return message.decision ||= { approved, key: newKey() };
}
