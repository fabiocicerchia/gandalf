// Bundle the extension host code. `vscode` is provided by the editor at runtime,
// so it stays external; everything else is inlined into one CJS file.
import * as esbuild from 'esbuild';

const production = process.argv.includes('--production');
const watch = process.argv.includes('--watch');
// The unit tests cover the vscode-free modules (parse/types), so they bundle
// and run under plain `node --test` with no editor and no test framework.
const tests = process.argv.includes('--tests');

const options = tests
  ? {
      entryPoints: ['src/test/parse.test.ts'],
      bundle: true,
      outdir: 'out',
      format: 'cjs',
      platform: 'node',
      target: 'node18',
      external: ['vscode', 'node:*'],
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
