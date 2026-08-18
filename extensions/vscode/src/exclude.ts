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
