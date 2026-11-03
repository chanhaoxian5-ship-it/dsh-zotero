import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

export const name = 'zotero-integration';
export const inject = ['skills'];
const directory = fileURLToPath(new URL('./skills/zotero/', import.meta.url));
const path = fileURLToPath(new URL('./skills/zotero/SKILL.md', import.meta.url));
const runner = fileURLToPath(new URL('./skills/zotero/scripts/run-zotero.mjs', import.meta.url));

export function apply(ctx) {
  ctx.skills.registerProvider(() => ({
    name: 'dsh-zotero',
    async list() {
      return [{ name: 'zotero', description: '连接本机 Zotero：搜索文献、读取附件索引全文、导入 RIS/BibTeX、导出引用。',
        provider: 'dsh-zotero', source: 'bundled', rank: 600,
        invocation: { modelInvocable: true, userInvocable: true },
        resourceBase: { kind: 'directory', path: directory }, path, locator: 'zotero' }];
    },
    async get(candidate, options = {}) {
      if (candidate.locator !== 'zotero') return undefined;
      const raw = await readFile(path, { encoding: 'utf8', signal: options.signal });
      return { ...candidate, content: raw.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/u, '')
        .replaceAll('{{ZOTERO_RUNNER_PS}}', runner.replaceAll("'", "''")) };
    },
  }));
}
