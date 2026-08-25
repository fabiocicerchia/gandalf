// Bundle the extension host code. `vscode` is provided by the editor at runtime,
// so it stays external; everything else is inlined into one CJS file.
import { readdirSync } from 'node:fs';

import * as esbuild from 'esbuild';

const production = process.argv.includes('--production');
const watch = process.argv.includes('--watch');
// The unit tests run under plain `node --test`, with no editor and no test
// framework: the vscode-free modules import nothing special, and the store gets
// the small shim in src/test/ aliased in for the `vscode` import.
const tests = process.argv.includes('--tests');
// `make bench` — same vscode-free bundling as the tests, one entry point.
const bench = process.argv.includes('--bench');

const options = bench
  ? {
      entryPoints: ['src/bench.ts'],
      bundle: true,
      outfile: 'out/bench.js',
      format: 'cjs',
      platform: 'node',
      target: 'node18',
      external: ['node:*'],
      alias: { vscode: './src/test/vscode-shim.ts' },
      logLevel: 'warning',
    }
  : tests
  ? {
      entryPoints: readdirSync('src/test')
        .filter((f) => f.endsWith('.test.ts'))
        .map((f) => `src/test/${f}`),
      bundle: true,
      outdir: 'out',
      format: 'cjs',
      platform: 'node',
      target: 'node18',
      external: ['node:*'],
      alias: { vscode: './src/test/vscode-shim.ts' },
      sourcemap: true,
      logLevel: 'info',
    }
  : {
      entryPoints: ['src/extension.ts'],
      bundle: true,
      outfile: 'dist/extension.js',
      format: 'cjs',
      platform: 'node',
      target: 'node18',
      external: ['vscode'],
      sourcemap: !production,
      minify: production,
      logLevel: 'info',
    };

if (watch) {
  const ctx = await esbuild.context(options);
  await ctx.watch();
} else {
  await esbuild.build(options);
}
