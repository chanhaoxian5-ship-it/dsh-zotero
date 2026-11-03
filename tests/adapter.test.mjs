import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { apply } from '../index.mjs';
import { pythonCandidates, main } from '../skills/zotero/scripts/run-zotero.mjs';
test('DSH provider discovers and loads absolute-path skill', async () => {
 let provider;
 apply({skills:{registerProvider(factory){provider=factory();}}});
 const [candidate]=await provider.list();
 assert.equal(candidate.name,'zotero');
 const loaded=await provider.get(candidate);
 assert.ok(loaded.content.includes('run-zotero.mjs'));
 assert.ok(!loaded.content.includes('{{ZOTERO_RUNNER_PS}}'));
 assert.ok(!loaded.content.startsWith('---'));
 assert.equal(await provider.get({locator:'other'}),undefined);
});
test('upstream Python preserved byte-for-byte', async () => {
 const script = await readFile(new URL('../skills/zotero/scripts/zotero.py',import.meta.url));
 assert.deepEqual(script, await readFile(new URL('../upstream/codex-zotero-0.1.2/skills/zotero/scripts/zotero.py',import.meta.url)));
 const blob = createHash('sha1').update(`blob ${script.length}\0`).update(script).digest('hex');
 assert.equal(blob, '0b12836d8133209d8f20d25bd1eba8904fd2833d');
});
test('explicit interpreter path is not split and invalid override fails clearly', () => {
 assert.deepEqual(pythonCandidates({ZOTERO_PYTHON:'C:/路径 with spaces/python.exe'}),[{command:'C:/路径 with spaces/python.exe',prefix:[]}]);
 assert.throws(()=>main(['status'],{...process.env,ZOTERO_PYTHON:'D:/nonexistent-zotero-python.exe'}),/Python >= 3.10/);
});
