#!/usr/bin/env node
/*
Determines container/app versions on demand.

What it does:
- Reads VERSION_MANIFEST.json for existing apps/components.
- Enumerates docker-compose services via `docker compose config` and extracts image tags.
- Computes deterministic tags for DQ-built images via `scripts/calculate_versions.sh --display`.
- Merges results into an apps map.

Usage:
  node scripts/determine_versions.js --print
  node scripts/determine_versions.js --write

Options:
  --manifest <path>   Path to VERSION_MANIFEST.json (default: repo root VERSION_MANIFEST.json)
  --print             Print computed apps JSON to stdout (default)
  --write             Update manifest file in place
  --pretty            Pretty-print output (default)
  --no-pretty         Compact JSON

Notes:
- Keeps existing `apps.ui` and `apps.api` as-is (release versions).
- Writes a trailing newline when updating JSON.
*/

const fs = require('fs');
const path = require('path');
const cp = require('child_process');

function parseArgs(argv) {
  const args = {
    manifest: null,
    mode: 'print',
    pretty: true,
  };

  for (let i = 2; i < argv.length; i++) {
    const token = argv[i];
    if (token === '--manifest') {
      args.manifest = argv[++i] || null;
    } else if (token === '--write') {
      args.mode = 'write';
    } else if (token === '--print') {
      args.mode = 'print';
    } else if (token === '--pretty') {
      args.pretty = true;
    } else if (token === '--no-pretty') {
      args.pretty = false;
    } else if (token === '-h' || token === '--help') {
      printHelpAndExit(0);
    } else {
      console.error(`Unknown arg: ${token}`);
      printHelpAndExit(2);
    }
  }

  return args;
}

function printHelpAndExit(code) {
  process.stdout.write(
    `Usage:\n` +
      `  node scripts/determine_versions.js --print\n` +
      `  node scripts/determine_versions.js --write\n` +
      `\n` +
      `Options:\n` +
      `  --manifest <path>   Path to VERSION_MANIFEST.json\n` +
      `  --print             Print computed apps JSON (default)\n` +
      `  --write             Update manifest file in place\n` +
      `  --pretty|--no-pretty JSON formatting\n`
  );
  process.exit(code);
}

function execOrThrow(command, cwd) {
  return cp.execSync(command, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    encoding: 'utf8',
    env: process.env,
  });
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function writeJson(filePath, payload, pretty) {
  const text = JSON.stringify(payload, null, pretty ? 2 : 0) + '\n';
  fs.writeFileSync(filePath, text, 'utf8');
}

function parseDockerComposeConfigForImages(composeConfigText) {
  // Minimal YAML parsing:
  // services:
  //   api:
  //     image: something:tag
  const lines = composeConfigText.split(/\r?\n/);
  const services = {};
  let currentService = null;
  let inServices = false;

  for (const line of lines) {
    if (!inServices) {
      if (line.trim() === 'services:') {
        inServices = true;
      }
      continue;
    }

    const serviceMatch = line.match(/^\s{2}([A-Za-z0-9_-]+):\s*$/);
    if (serviceMatch) {
      currentService = serviceMatch[1];
      continue;
    }

    if (!currentService) continue;

    const imageMatch = line.match(/^\s{4}image:\s*(.+?)\s*$/);
    if (imageMatch) {
      services[currentService] = imageMatch[1];
      continue;
    }

    // End of services section when a top-level key starts.
    if (!line.startsWith(' ') && line.trim().endsWith(':')) {
      break;
    }
  }

  return services;
}

function versionFromImageRef(imageRef) {
  const ref = String(imageRef || '').trim();
  if (!ref) return 'unknown';

  // Digests: repo@sha256:...
  if (ref.includes('@sha256:')) {
    return ref.split('@sha256:')[1] ? `sha256:${ref.split('@sha256:')[1]}` : 'unknown';
  }

  // Remove any registry path; keep tag if present.
  // Examples:
  // - grafana/loki:3.6.4 -> 3.6.4
  // - prom/prometheus:v3 -> v3
  // - postgres:15-alpine -> 15-alpine
  // - internal.euprod/.../dq-api:latest -> latest
  const lastColonIndex = ref.lastIndexOf(':');
  const lastSlashIndex = ref.lastIndexOf('/');

  // If there is a colon after the last slash, treat as tag separator.
  if (lastColonIndex > lastSlashIndex) {
    return ref.slice(lastColonIndex + 1).trim() || 'unknown';
  }

  return 'latest';
}

function parseCalculatedTags(outputText) {
  // Extract lines like: DQ_ENGINE_TAG:    0.7-f86ee12
  const tags = {};
  for (const line of outputText.split(/\r?\n/)) {
    const match = line.match(/^(DQ_[A-Z0-9_]+_TAG):\s+(.+?)\s*$/);
    if (match) {
      tags[match[1]] = match[2].trim();
    }
  }
  return tags;
}

function main() {
  const args = parseArgs(process.argv);
  const repoRoot = path.resolve(__dirname, '..');
  const manifestPath = path.resolve(repoRoot, args.manifest || 'VERSION_MANIFEST.json');

  if (!fs.existsSync(manifestPath)) {
    console.error(`Manifest not found: ${manifestPath}`);
    process.exit(1);
  }

  const manifest = readJson(manifestPath);
  const existingApps = (manifest && typeof manifest === 'object' && manifest.apps && typeof manifest.apps === 'object') ? manifest.apps : {};

  let composeConfig;
  try {
    composeConfig = execOrThrow('docker compose config', repoRoot);
  } catch (err) {
    console.error('Failed to run `docker compose config` (is Docker running?).');
    console.error(String(err?.stderr || err?.message || err));
    process.exit(1);
  }

  const serviceImages = parseDockerComposeConfigForImages(composeConfig);
  const serviceVersions = {};
  for (const [serviceName, imageRef] of Object.entries(serviceImages)) {
    serviceVersions[serviceName] = versionFromImageRef(imageRef);
  }

  // Deterministic tags for internal images.
  let calculatedTags = {};
  try {
    const out = execOrThrow('bash scripts/calculate_versions.sh --display 2>/dev/null', repoRoot);
    calculatedTags = parseCalculatedTags(out);
  } catch {
    // Non-fatal: we can still report compose-derived tags.
    calculatedTags = {};
  }

  const internalOverrides = {
    base: calculatedTags.DQ_BASE_TAG,
    db: calculatedTags.DQ_DB_TAG,
    keycloak: calculatedTags.DQ_KEYCLOAK_TAG,
    'dq-engine': calculatedTags.DQ_ENGINE_TAG,
    'profiling-worker': calculatedTags.DQ_PROFILING_TAG,
    frontend: calculatedTags.DQ_FRONTEND_TAG,
    kong: calculatedTags.DQ_KONG_TAG,
  };

  // Merge:
  // - Start with existing apps (to preserve ui/api release versions)
  // - Add docker-compose service versions
  // - Apply overrides for internal services when available
  const mergedApps = { ...existingApps, ...serviceVersions };
  for (const [key, value] of Object.entries(internalOverrides)) {
    if (typeof value === 'string' && value.trim()) {
      mergedApps[key] = value.trim();
    }
  }

  if (args.mode === 'write') {
    const updated = {
      ...manifest,
      apps: mergedApps,
    };
    writeJson(manifestPath, updated, true);
    process.stdout.write(`Updated manifest apps: ${path.relative(repoRoot, manifestPath)}\n`);
    return;
  }

  const output = args.pretty ? JSON.stringify(mergedApps, null, 2) : JSON.stringify(mergedApps);
  process.stdout.write(output + '\n');
}

main();
