const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Get version from git tags (latest tag)
let version = '0.0.0';
let lastCommit = 'unknown';
let commitDate = 'N/A';

try {
  // Get the latest git tag (version)
  version = execSync('git describe --tags --abbrev=0', { encoding: 'utf-8' }).trim().replace(/^v/, '');
} catch (e) {
  console.warn('Could not get git tag, falling back to package.json version');
  const packageJson = require('../package.json');
  version = packageJson.version;
}

try {
  lastCommit = execSync('git rev-parse --short HEAD', { encoding: 'utf-8' }).trim();
  commitDate = execSync('git log -1 --format=%ci', { encoding: 'utf-8' }).trim();
} catch (e) {
  console.warn('Could not get git info:', e.message);
}

const buildTimestamp = new Date().toISOString();

const content = `// This file is auto-generated during build
// Run: node scripts/generate-version.js

export const VERSION_INFO = {
  version: '${version}',
  lastCommit: '${lastCommit}',
  commitDate: '${commitDate}',
  buildTimestamp: '${buildTimestamp}',
};
`;

const outputPath = path.join(__dirname, '../src/version.ts');
fs.writeFileSync(outputPath, content);
console.log('Generated version.ts with:', { version, lastCommit, commitDate, buildTimestamp });
