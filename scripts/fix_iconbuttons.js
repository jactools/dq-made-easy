#!/usr/bin/env node
// Legacy-only helper for the historical dq-rules-ui subtree.
// Do not use this script as part of the supported dq-ui frontend workflow.
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', 'dq-rules-ui', 'src');
const files = [];

function walk(dir) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    const s = fs.statSync(p);
    if (s.isDirectory()) walk(p);
    else if (s.isFile() && (p.endsWith('.tsx') || p.endsWith('.ts') || p.endsWith('.jsx') || p.endsWith('.js'))) files.push(p);
  }
}

walk(root);

const occurrences = [];

for (const file of files) {
  const src = fs.readFileSync(file, 'utf8');
  const lines = src.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.includes('<IconButton')) {
      // scan the tag block (up to next 6 lines) for an icon= prop
      let block = line;
      let j = i + 1;
      while (j < Math.min(lines.length, i + 10) && !/\/>|>/.test(lines[j])) {
        block += '\n' + lines[j];
        j++;
      }
      // include the closing line
      if (j < lines.length) block += '\n' + lines[j];
      const hasIcon = /\bicon\s*=\s*[{\"']/.test(block);
      if (!hasIcon) {
        occurrences.push({ file, line: i + 1, preview: line.trim() });
      }
    }
  }
}

if (occurrences.length === 0) {
  console.log('No IconButton usages lacking an icon prop were found.');
  process.exit(0);
}

console.log('Found IconButton usages without icon prop:');
for (const o of occurrences) {
  console.log(`${o.file}:${o.line}  --> ${o.preview}`);
}

// If you want the script to auto-patch, implement changes here.
// For safety this script only reports occurrences.
process.exit(0);
