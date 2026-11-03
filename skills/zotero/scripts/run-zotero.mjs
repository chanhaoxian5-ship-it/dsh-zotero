import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

export function pythonCandidates(env = process.env, platform = process.platform, home = homedir()) {
  if (env.ZOTERO_PYTHON) return [{ command: env.ZOTERO_PYTHON, prefix: [] }];
  const bundled = join(env.DSH_HOME || join(home, '.dsh'), 'dsh-runtimes', 'dsh-primary-runtime',
    'dependencies', 'python', ...(platform === 'win32' ? ['python.exe'] : ['bin', 'python3']));
  return [...(existsSync(bundled) ? [{ command: bundled, prefix: [] }] : []),
    ...(platform === 'win32' ? [{ command: 'python', prefix: [] }, { command: 'py', prefix: ['-3'] }]
      : [{ command: 'python3', prefix: [] }, { command: 'python', prefix: [] }])];
}

export function main(args, env = process.env) {
  const runtimeEnv = { ...env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1' };
  const python = pythonCandidates(env).find(({ command, prefix }) => spawnSync(command,
    [...prefix, '-c', 'import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)'],
    { env: runtimeEnv, shell: false, windowsHide: true, stdio: 'ignore', timeout: 10000 }).status === 0);
  if (!python) throw new Error('需要 Python >= 3.10；可通过 ZOTERO_PYTHON 指定 python.exe 的完整路径。');
  const helper = fileURLToPath(new URL('./zotero.py', import.meta.url));
  const result = spawnSync(python.command, [...python.prefix, '-X', 'utf8', helper, ...args],
    { env: runtimeEnv, shell: false, windowsHide: true, stdio: 'inherit' });
  if (result.error) throw result.error;
  return result.status ?? 1;
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try { process.exitCode = main(process.argv.slice(2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
