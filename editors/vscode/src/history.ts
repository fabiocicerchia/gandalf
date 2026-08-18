/**
 * Score over time, from data gandalf already keeps.
 *
 * Every CLI run appends a line to `.gandalf-trend.jsonl` — commit, score,
 * timestamp — which is how the report's "(+5 vs prev)" is computed. Nothing has
 * ever read it back except gandalf itself. Joined against `git log` it answers
 * the question a single scorecard cannot: is this getting better?
 *
 * Editor scans deliberately do not write to that log (a scan per save would
 * swamp a history meant to be per-commit), so entries come from CLI and CI runs
 * and from scanning a commit explicitly.
 */

export interface TrendEntry {
  commit: string;
  score: number;
  at: string;
}

export interface Commit {
  short: string;
  subject: string;
  date: string;
}

/**
 * The newest score per commit. The log is append-only, so a commit rescanned
 * later appears more than once and the last line wins.
 */
export function parseTrend(text: string): Map<string, TrendEntry> {
  const out = new Map<string, TrendEntry>();
  for (const line of text.split('\n')) {
    if (!line.trim().startsWith('{')) continue;
    try {
      const raw = JSON.parse(line) as Record<string, unknown>;
      const commit = typeof raw.commit === 'string' ? raw.commit : '';
      const score = typeof raw.score === 'number' ? raw.score : NaN;
      if (!commit || Number.isNaN(score)) continue;
      out.set(commit, {
        commit,
        score,
        at: typeof raw.generated_at === 'string' ? raw.generated_at : '',
      });
    } catch {
      // A truncated final line is normal for an append-only log.
    }
  }
  return out;
}

/** `git log --format=%h%x1f%s%x1f%cs`, newest first. */
export function parseLog(stdout: string): Commit[] {
  return stdout
    .split('\n')
    .map((line) => line.split('\x1f'))
    .filter((parts) => parts.length === 3 && parts[0])
    .map(([short, subject, date]) => ({ short, subject, date }));
}

const TICKS = '▁▂▃▄▅▆▇█';

/**
 * A score history as one line of text. A chart would mean a webview, and the
 * shape of the line is the whole question — eight blocks answer it natively.
 * Scaled across the observed range, not 0–100: the interesting movement in a
 * repository that sits in the eighties is within those eighties.
 */
export function sparkline(scores: number[]): string {
  if (scores.length === 0) return '';
  const low = Math.min(...scores);
  const high = Math.max(...scores);
  const span = high - low;
  return scores
    .map((s) => TICKS[span === 0 ? 0 : Math.round(((s - low) / span) * (TICKS.length - 1))])
    .join('');
}

/** "+5", "-3", or "" for the first scored commit in the series. */
export function delta(score: number, previous: number | undefined): string {
  if (previous === undefined) return '';
  const d = score - previous;
  return d === 0 ? '±0' : d > 0 ? `+${d}` : `${d}`;
}
