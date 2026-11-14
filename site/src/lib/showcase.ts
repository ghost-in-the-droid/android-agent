/** Showcase media comes from the same clean-demo catalog as Skill Hub pages. */
import { loadHub } from './hub/registry';

export interface DemoSpec {
 demo: string; title: string; category: string; docs: string;
 skill: string; action: string; video: string; poster: string;
}
export const CATEGORY_LABELS: Record<string,string> = {'skill-demos':'Skill demos'};
export function loadAllSpecs(): DemoSpec[] {
 return loadHub().skills.flatMap((skill)=>skill.demoClips.filter((clip)=>clip.action).map((clip)=>({
  demo:`skill-${skill.author}-${skill.slug}-${clip.action}`,
  title:`${skill.name}: ${clip.action}`, category:'skill-demos',
  docs:`/skills/${skill.id}/`,skill:skill.id,action:clip.action!,
  video:clip.url,poster:skill.iconUrl ?? '/favicon.svg',
 })));
}
export function loadSpec(slug:string): DemoSpec|null {return loadAllSpecs().find((s)=>s.demo===slug) ?? null;}
export function loadSnippet(_slug:string): string {return '';}
export function demoAssets(slug:string) {
 const spec=loadSpec(slug);
 if (!spec) throw new Error(`No clean showcase clip: ${slug}`);
 return {poster:spec.poster,video:spec.video};
}
export function loadCopy(): Record<string,{title:string;hook?:string;sizzle_order?:number}> {
 return Object.fromEntries(loadAllSpecs().map((s)=>[s.demo,{title:s.title}]));
}
