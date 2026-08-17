// Apache-2.0 §4 wants LICENSE and NOTICE shipped with anything we distribute,
// and a .vsix is a distribution. They are copied from the repository root at
// package time rather than kept as a second copy in git.
import { copyFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, '..', '..', '..');

for (const name of ['LICENSE', 'NOTICE']) {
  copyFileSync(join(repoRoot, name), join(here, '..', name));
  console.log(`copied ${name}`);
}
