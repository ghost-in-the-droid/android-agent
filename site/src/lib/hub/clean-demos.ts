/** Presentation-only catalog. Never a source of runs, scores or verification credit. */
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { resolve, sep } from 'node:path';

export interface CleanDemo {
 skill: string; action: string; path: string; sha256: string;
 purpose: 'demo'; outcome: 'pass'; reset_mode: 'pm_clear' | 'verified_ui_reset';
 fixture: { verified: true; seed?: string };
 protocol: { event: string; at: string }[];
 file: string; kind: 'webm';
}

export function readCleanDemos(root: string): CleanDemo[] {
 const catalog=resolve(root,'demo-catalog.json');
 if (!existsSync(catalog)) return [];
 const data=JSON.parse(readFileSync(catalog,'utf8'));
 if (data.schema_version!==1 || !Array.isArray(data.clips)) throw new Error('Invalid clean demo catalog');
 const seen=new Set<string>(), realRoot=realpathSync(root);
 return data.clips.map((clip: CleanDemo) => {
  const key=`${clip.skill}/${clip.action}`;
  if (!/^[a-z][a-z0-9_-]*\/[a-z][a-z0-9_-]*$/.test(clip.skill) || !/^[a-z][a-z0-9_-]*$/.test(clip.action)) throw new Error('Invalid clean demo identity');
  if (seen.has(key)) throw new Error(`duplicate clean demo: ${key}`);
  seen.add(key);
  if (clip.path!==`${clip.skill}/demos/${clip.action}.webm`) throw new Error(`Invalid clean demo path: ${key}`);
  const file=realpathSync(resolve(root,clip.path));
  if (!file.startsWith(realRoot+sep) || statSync(file).size>3*1024*1024) throw new Error(`Invalid clean demo path or size: ${key}`);
  if (createHash('sha256').update(readFileSync(file)).digest('hex')!==clip.sha256) throw new Error(`Clean demo hash mismatch: ${key}`);
  if (clip.purpose!=='demo' || clip.outcome!=='pass' || clip.fixture?.verified!==true) throw new Error(`Unverified clean demo: ${key}`);
  const reset=clip.reset_mode==='pm_clear'?'pm_clear':clip.reset_mode==='verified_ui_reset'?'ui_reset_verified':null;
  const required=[...(reset==='pm_clear'?['force_stop']:[]),reset,'seed_verified','home_verified','capture_started','app_launched','action_started','action_finished','capture_stopped'];
  let previous=-1, previousTime=-Infinity;
  for (const event of required) {
   const index=clip.protocol?.findIndex((entry)=>entry.event===event) ?? -1;
   const time=Date.parse(clip.protocol?.[index]?.at);
   if (!event || index<=previous || !Number.isFinite(time) || time<previousTime) throw new Error(`Invalid clean demo protocol: ${key}`);
   previous=index; previousTime=time;
  }
  return {...clip,file,kind:'webm'};
 });
}
