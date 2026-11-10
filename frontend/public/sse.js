// SSE frames can span TCP chunks, UTF-8 code points and CRLF boundaries.
export async function readEvents(body, onEvent) {
  if (!body) throw new Error('没有收到事件流');
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const drain = () => {
    let match;
    while ((match = /\r?\n\r?\n/.exec(buffer))) {
      const frame = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0].length);
      let event = 'message'; const data = [];
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
      }
      if (data.length) onEvent(event, JSON.parse(data.join('\n')));
    }
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) { buffer += decoder.decode(); drain(); break; }
      buffer += decoder.decode(value, { stream: true }); drain();
      if (buffer.length > 1_000_000) throw new Error('事件长度异常');
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}
