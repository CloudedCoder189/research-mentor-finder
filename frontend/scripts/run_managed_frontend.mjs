// Preserve only operational categories; discard raw output and request information.
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
const root = path.resolve(process.env.RETENTION_ROOT ?? '');
const rejectLinks = (value) => {
  for (let current = value; ; current = path.dirname(current)) {
    if (fs.lstatSync(current).isSymbolicLink()) throw new Error('Linked managed storage rejected');
    if (path.dirname(current) === current) break;
  }
};
rejectLinks(root);
rejectLinks(path.join(root, 'logs'));
const marker = JSON.parse(fs.readFileSync(path.join(root, 'store.json'), 'utf8'));
if (marker.schema !== 1 || !/^[a-f0-9]{64}$/.test(marker.database)) throw new Error('Invalid managed store');
function log(event) {
  const now = new Date();
  const file = path.join(root, 'logs', `frontend-${now.toISOString().slice(0, 10)}.jsonl`);
  try {
    if (fs.existsSync(file)) rejectLinks(file);
    fs.appendFileSync(file, JSON.stringify({time: now.toISOString(), event}) + '\n', {mode: 0o600});
  } catch { /* Never forward raw output if logging fails. */ }
}
const child = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'start', '-H', '127.0.0.1', '-p', process.env.MANAGED_FRONTEND_PORT ?? '13310'], {stdio: ['ignore', 'pipe', 'pipe']});
child.stdout.on('data', () => log('frontend_output'));
child.stderr.on('data', () => log('frontend_error'));
child.on('error', () => {log('frontend_start_failed'); process.exitCode = 1;});
child.on('exit', (code) => {log('frontend_stopped'); process.exitCode = code ?? 1;});
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
log('frontend_started');
