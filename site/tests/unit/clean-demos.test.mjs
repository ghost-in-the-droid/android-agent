import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { readCleanDemos } from '../../src/lib/hub/clean-demos.ts';

function fixture(run) {
 const root=mkdtempSync(join(tmpdir(),'clean-demos-'));
 try {
  mkdirSync(join(root,'ghost/calc/demos'),{recursive:true});
  const bytes=Buffer.from('recorded clip');writeFileSync(join(root,'ghost/calc/demos/calculate.webm'),bytes);
  const clip={skill:'ghost/calc',action:'calculate',path:'ghost/calc/demos/calculate.webm',sha256:createHash('sha256').update(bytes).digest('hex'),purpose:'demo',outcome:'pass',reset_mode:'pm_clear',fixture:{verified:true},protocol:['force_stop','pm_clear','seed_verified','home_verified','capture_started','app_launched','action_started','action_finished','capture_stopped'].map((event,i)=>({event,at:new Date(i*1000).toISOString()}))};
  const write=()=>writeFileSync(join(root,'demo-catalog.json'),JSON.stringify({schema_version:1,clips:[clip]}));
  run({root,clip,write});
 } finally {rmSync(root,{recursive:true,force:true});}
}
test('no catalog means no clean media, with no legacy fallback',()=>fixture(({root})=>assert.deepEqual(readCleanDemos(root),[])));
test('accepts hash-bound HOME-before-launch demo without changing evidence',()=>fixture(({root,write})=>{write();const [clip]=readCleanDemos(root);assert.equal(clip.action,'calculate');assert.equal(clip.kind,'webm');assert.equal(clip.purpose,'demo');}));
test('rejects a clip whose bytes were replaced after review',()=>fixture(({root,write})=>{write();writeFileSync(join(root,'ghost/calc/demos/calculate.webm'),'old clip');assert.throws(()=>readCleanDemos(root),/hash/);}));
test('rejects recording started after launch and missing resets',()=>fixture(({root,clip,write})=>{[clip.protocol[4],clip.protocol[5]]=[clip.protocol[5],clip.protocol[4]];write();assert.throws(()=>readCleanDemos(root),/protocol/);clip.protocol=[];write();assert.throws(()=>readCleanDemos(root),/protocol/);}));
test('rejects escaping paths and duplicate action declarations',()=>fixture(({root,clip,write})=>{clip.path='../secret.webm';write();assert.throws(()=>readCleanDemos(root),/path/);clip.path='ghost/calc/demos/calculate.webm';writeFileSync(join(root,'demo-catalog.json'),JSON.stringify({schema_version:1,clips:[clip,clip]}));assert.throws(()=>readCleanDemos(root),/duplicate/);}));
