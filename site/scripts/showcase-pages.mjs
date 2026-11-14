import { readFileSync } from 'node:fs';
import yaml from 'js-yaml';
const manifest = yaml.load(readFileSync(new URL('../../skillhub/showcase.yml', import.meta.url), 'utf8'));
export const showcasePages = ['/skills/showcase/', ...new Set(manifest.skills.map(({ ref }) => `/skills/${ref}/`))];
export const showcaseViewports = [{ width: 1280, height: 900 }, { width: 390, height: 844 }];
