/** Fail when the built SPA references an external network resource. */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const dist = join(root, 'dist');

const externalHosts = [
  'fonts.googleapis.com',
  'fonts.gstatic.com',
  'cdn.jsdelivr.net',
  'unpkg.com',
  'cdnjs.cloudflare.com',
  'google-analytics.com',
  'googletagmanager.com',
  'sentry.io',
  'telemetry',
];

function files(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

const problems = [];

for (const path of files(dist)) {
  const text = readFileSync(path, 'utf8');
  const relative = path.slice(root.length + 1);

  // HTML/CSS attributes and imports must stay local.
  for (const match of text.matchAll(/(?:src|href)\s*=\s*["'](?:https?:)?\/\/[^"']+/gi)) {
    problems.push(`${relative}: externes Attribut ${match[0]}`);
  }
  for (const match of text.matchAll(/url\(\s*["']?(?:https?:)?\/\//gi)) {
    problems.push(`${relative}: externes url()`);
  }

  // Code must not fetch or open absolute endpoints.
  for (const match of text.matchAll(/(?:fetch|WebSocket|EventSource)\(\s*["'`](?:https?|wss?):\/\//gi)) {
    problems.push(`${relative}: absoluter Netzwerkaufruf ${match[0]}`);
  }
  for (const match of text.matchAll(/import\(\s*["'`]https?:\/\//gi)) {
    problems.push(`${relative}: externer dynamischer Import`);
  }

  for (const host of externalHosts) {
    if (text.includes(host)) problems.push(`${relative}: externe Domain ${host}`);
  }
}

if (problems.length > 0) {
  console.error('Externe Ressourcen im Build gefunden:');
  for (const problem of problems) console.error(`- ${problem}`);
  process.exit(1);
}

console.log('Build enthält keine externen Netzwerkressourcen.');
