// Serves the skill.yaml JSON Schema exported by tools/export_schema.py.
import type { APIRoute } from 'astro';
import schema from '../../../lib/hub/skill.schema.json';

export const GET: APIRoute = () =>
	new Response(JSON.stringify(schema, null, 2), { headers: { 'Content-Type': 'application/schema+json' } });
