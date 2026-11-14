import assert from 'node:assert/strict';
import worker from './worker.mjs';
const payload = {schema_version:1, skill:'ghost/google_maps', app_version:'25.0.0', outcome:'passed', os:'android', backend:'device', install_id:'12345678-1234-4234-8234-123456789012'};
const writes = [];
const env = {TELEMETRY_CATALOG:JSON.stringify({'ghost/google_maps':['25.0.0']}), EVENTS:{async put(...args){writes.push(args);}}};
const request = body => new Request('https://example.invalid/run', {method:'POST', headers:{'Content-Type':'application/json', 'CF-Connecting-IP':'192.0.2.1'}, body:JSON.stringify(body)});
assert.equal((await worker.fetch(request(payload), env)).status, 204);
assert.equal(writes.length, 1);
const stored = JSON.parse(writes[0][1]);
assert.equal(stored.skill, payload.skill);
assert.ok(stored.timestamp);
assert.ok(!writes[0][1].includes('192.0.2.1'));
for (const invalid of [{...payload, text:'private'}, {...payload, ip:'192.0.2.1'}, {...payload, outcome:'private text'}, {...payload, skill:'192.0.2.1'}, {...payload, app_version:'private'}, {...payload, install_id:'192.0.2.1'}, {...payload, os:'arbitrary'}, {...payload, backend:'arbitrary'}, {...payload, schema_version:true}]) {
  assert.equal((await worker.fetch(request(invalid), env)).status, 400);
}
assert.equal((await worker.fetch(request(payload), {...env, TELEMETRY_CATALOG:'{}'})).status,400);
assert.equal((await worker.fetch(new Request('https://example.invalid'), env)).status,405);
assert.equal((await worker.fetch(request({text:'x'.repeat(3000)}),env)).status,413);
assert.equal(writes.length,1);
console.log('telemetry worker tests passed');

assert.equal((await worker.fetch(request({...payload, app_version:'192.0.2.1'}), {...env, TELEMETRY_CATALOG:JSON.stringify({'ghost/google_maps':['192.0.2.1']})})).status,400);
