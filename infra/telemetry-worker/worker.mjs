const fields = ['schema_version', 'skill', 'app_version', 'outcome', 'os', 'backend', 'install_id'];
export function validate(payload, catalog) {
  if (!payload || Array.isArray(payload) || typeof payload !== 'object' ||
      Object.keys(payload).length !== fields.length || fields.some(k => !Object.hasOwn(payload, k))) return false;
  return payload.schema_version === 1 &&
    typeof payload.skill === 'string' && /^[a-z0-9][a-z0-9_-]{0,63}\/[a-z0-9][a-z0-9_-]{0,63}$/.test(payload.skill) &&
    typeof payload.app_version === 'string' && /^[0-9][0-9A-Za-z.+_-]{0,63}$/.test(payload.app_version) &&
    !/^\d{1,3}(\.\d{1,3}){3}$/.test(payload.app_version) &&
    Object.hasOwn(catalog, payload.skill) && Array.isArray(catalog[payload.skill]) &&
    catalog[payload.skill].includes(payload.app_version) &&
    ['passed', 'failed'].includes(payload.outcome) && ['android', 'ios'].includes(payload.os) &&
    ['device', 'fake'].includes(payload.backend) &&
    typeof payload.install_id === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(payload.install_id);
}
export default {
  async fetch(request, env) {
    if (request.method !== 'POST') return new Response('Method not allowed', {status: 405});
    if ((request.headers.get('content-type') || '').split(';')[0] !== 'application/json') return new Response('JSON required', {status: 415});
    // Stream with a hard limit; do not trust Content-Length or retain headers/IPs.
    const reader = request.body?.getReader();
    if (!reader) return new Response('Invalid payload', {status: 400});
    const chunks = []; let size = 0;
    while (true) {
      const {done, value} = await reader.read(); if (done) break;
      size += value.length;
      if (size > 2048) { await reader.cancel(); return new Response('Too large', {status: 413}); }
      chunks.push(value);
    }
    try {
      const bytes = new Uint8Array(size); let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
      const payload = JSON.parse(new TextDecoder().decode(bytes));
      const catalog = JSON.parse(env.TELEMETRY_CATALOG || '{}');
      if (!validate(payload, catalog)) return new Response('Invalid payload', {status: 400});
      const timestamp = new Date().toISOString();
      // Each immutable object is one JSON line in the logical append-only log.
      // Avoid read/modify/write of a shared daily object, which loses concurrent events.
      await env.EVENTS.put(`events/${timestamp.slice(0,10)}/${crypto.randomUUID()}.jsonl`,
        JSON.stringify({...payload, timestamp}) + '\n', {httpMetadata: {contentType: 'application/x-ndjson'}});
      return new Response(null, {status: 204});
    } catch { return new Response('Unable to accept event', {status: 400}); }
  }
};
