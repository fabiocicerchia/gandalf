// Files the .vsix carries that are not kept as a second copy in git.
//
// LICENSE and NOTICE because Apache-2.0 §4 wants them shipped with anything we
// distribute, and a .vsix is a distribution. CHANGELOG.md because the
// Marketplace renders one as a tab, and there is exactly one changelog —
// release-please's, at the repository root. All three are gitignored here.
import { copyFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, '..', '..', '..');

for (const name of ['LICENSE', 'NOTICE', 'CHANGELOG.md']) {
  copyFileSync(join(repoRoot, name), join(here, '..', name));
  console.log(`copied ${name}`);
}
