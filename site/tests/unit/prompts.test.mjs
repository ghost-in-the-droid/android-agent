import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { readActionPrompts } from '../../src/lib/hub/prompts.ts';

function fixture(run) {
 const dir = mkdtempSync(join(tmpdir(), 'hub-prompts-'));
 try { run(dir, (raw) => writeFileSync(join(dir, 'skill.yaml'), JSON.stringify(raw))); }
 finally { rmSync(dir, { recursive: true, force: true }); }
}
test('site loader preserves primary prompts and at most three distinct variants', () => fixture((dir, write) => {
 write({ actions: [{ name: 'calculate', ref_prompt: '  Calculate {expression}  ', test_case: { ref_prompt_variants: ['Calculate {expression}', '  Work out {expression} ', '', null, 'Compute {expression}', 'Solve {expression}', 'Fourth variant'] } }] });
 assert.deepEqual(readActionPrompts(dir, 'ghost/calculator', ['calculate']).calculate, { primary: 'Calculate {expression}', variants: ['Work out {expression}', 'Compute {expression}', 'Solve {expression}'] });
}));
test('site loader fails with skill/action context for absent or blank ref_prompt', () => fixture((dir, write) => {
 for (const ref_prompt of [undefined, null, '', '   ', 42]) {
  write({ actions: [{ name: 'calculate', ref_prompt }] });
  assert.throws(() => readActionPrompts(dir, 'ghost/calculator', ['calculate']), /ghost\/calculator\/calculate: missing required ref_prompt/);
 }
 write({ actions: [] });
 assert.throws(() => readActionPrompts(dir, 'ghost/calculator', ['calculate']), /ghost\/calculator\/calculate/);
 assert.throws(() => readActionPrompts(null, 'ghost/calculator', ['calculate']), /ghost\/calculator: cannot read/);
}));
