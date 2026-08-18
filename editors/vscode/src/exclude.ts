/**
 * Turning the editor's excluded folders into gandalf's.
 *
 * VS Code already knows what not to look at — `files.exclude` and
 * `search.exclude` are where people put `node_modules`, build output and
 * vendored trees — so the extension reads those rather than asking for the same
 * list a second time. The two glob dialects differ enough to need translating:
 * VS Code anchors with a leading double-star, gandalf matches a bare name
 * against any path segment (see `is_ignored` in gandalf/plugins.py, which
 * these rules mirror).
 */

/** VS Code exclude maps are `{glob: true}`, `{glob: false}` or `{glob: {when}}`. */
export function enabledGlobs(map: unknown): string[] {
  if (!map || typeof map !== 'object') return [];
  // Only an unconditional `true`: a `when` clause depends on sibling files,
  // which is a question about the workspace, not a pattern gandalf could apply.
  return Object.entries(map as Record<string, unknown>)
    .filter(([, on]) => on === true)
    .map(([glob]) => glob);
}

/**
 * Expand a single level of `{a,b}` alternation, which VS Code globs allow and
 * gandalf's fnmatch does not. Nested braces are left alone rather than
 * half-expanded — better an unexpanded pattern than a wrong one.
 */
export function expandBraces(glob: string): string[] {
  const open = glob.indexOf('{');
  const close = glob.indexOf('}', open + 1);
  if (open === -1 || close === -1) return [glob];
  const inner = glob.slice(open + 1, close);
  if (inner.includes('{')) return [glob];
  const prefix = glob.slice(0, open);
  const suffix = glob.slice(close + 1);
  return inner.split(',').flatMap((choice) => expandBraces(prefix + choice.trim() + suffix));
}

/**
 * VS Code glob → gandalf pattern. `**` is how VS Code says "at any depth", which
 * is what a bare name already means to gandalf, so the leading and trailing
 * `**` are dropped rather than passed through to a matcher that would read them
 * as two literal stars.
 */
export function toGandalfPattern(glob: string): string {
  let pattern = glob.trim().replace(/\\/g, '/');
  while (pattern.startsWith('**/')) pattern = pattern.slice(3);
  while (pattern.endsWith('/**')) pattern = pattern.slice(0, -3);
  pattern = pattern.replace(/\/+$/, '');
  // A bare `**` excludes everything; that is never what someone means here.
  return pattern === '**' || pattern === '*' ? '' : pattern;
}

/** Everything the editor and the settings say to skip, translated and deduped. */
export function excludePatterns(...sources: (string[] | undefined)[]): string[] {
  const out = new Set<string>();
  for (const source of sources) {
    for (const glob of source ?? []) {
      for (const expanded of expandBraces(glob)) {
        const pattern = toGandalfPattern(expanded);
        if (pattern) out.add(pattern);
      }
    }
  }
  return [...out];
}

/** fnmatch semantics, so a pattern means here what it will mean to gandalf. */
const compiled = new Map<string, RegExp>();

function matcher(pattern: string): RegExp {
  let re = compiled.get(pattern);
  if (re) return re;
  let source = '';
  for (let i = 0; i < pattern.length; i++) {
    const c = pattern[i];
    if (c === '*') source += '.*'; // fnmatch's `*` spans separators
    else if (c === '?') source += '.';
    else if (c === '[') {
      const end = pattern.indexOf(']', i + 1);
      if (end === -1) source += '\\[';
      else {
        const body = pattern.slice(i + 1, end).replace(/^!/, '^');
        source += `[${body}]`;
        i = end;
      }
    } else source += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  }
  re = new RegExp(`^(?:${source})$`, 's');
  compiled.set(pattern, re);
  return re;
}

/**
 * Whether a repo-relative path is excluded. Mirrors `is_ignored` in
 * gandalf/plugins.py — the same table of cases is asserted against both, since
 * the extension uses this to avoid launching a scan gandalf would find nothing
 * in, and disagreeing with it would mean silently skipping a real file.
 */
export function isExcluded(rel: string, patterns: string[]): boolean {
  const p = rel.replace(/\\/g, '/').replace(/^\.\//, '');
  if (!p) return false;
  const segments = p.split('/');
  for (const raw of patterns) {
    const pattern = raw
      .trim()
      .replace(/\\/g, '/')
      .replace(/^\.\//, '')
      .replace(/\/+$/, '');
    if (!pattern) continue;
    const anchored = pattern.includes('/');
    if (!/[*?[]/.test(pattern)) {
      if (anchored ? p === pattern || p.startsWith(`${pattern}/`) : segments.includes(pattern)) {
        return true;
      }
      continue;
    }
    const re = matcher(pattern);
    if (re.test(p)) return true;
    if (anchored) {
      if (p === pattern || p.startsWith(`${pattern}/`)) return true;
    } else if (segments.some((segment) => re.test(segment))) return true;
  }
  return false;
}
