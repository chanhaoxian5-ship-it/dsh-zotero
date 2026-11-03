import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { pythonCandidates } from '../skills/zotero/scripts/run-zotero.mjs';
const python = pythonCandidates().find(({command, prefix}) => spawnSync(command,
  [...prefix, '-c', 'import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)'],
  {stdio:'ignore', windowsHide:true, timeout:10000}).status === 0);
if (!python) throw Error('Tests require Python >=3.10');
const result = spawnSync(python.command, [...python.prefix, '-X', 'utf8', '-m', 'unittest',
  'discover', '-s', fileURLToPath(new URL('./',import.meta.url)), '-p', 'test_*.py', '-v'],
  {stdio:'inherit', windowsHide:true, env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
if(result.error)throw result.error;
process.exitCode=result.status ?? 1;
