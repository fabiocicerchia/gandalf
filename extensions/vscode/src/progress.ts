/**
 * Reading gandalf's progress line as it happens.
 *
 * `gandalf/progress.py` already reports what a run is doing — it writes one
 * self-overwriting line to stderr, `\r ESC[K [2/3] Running 37 gates  [███░░░]
 * 12/37 semgrep`, and `GANDALF_PROGRESS=1` turns it on even without a TTY. So
 * the extension doesn't have to guess at progress: it parses that line.
 *
 * Two wrinkles the parser handles. Redraws are separated by `\r` with no
 * trailing newline, so a state is only read once the *next* redraw delimits it —
 * one update of lag, deliberately: parsing the unterminated tail instead would
 * mean a split read could surface a truncated line ("[2/3] Runn") whose
 * percentage is lower than what was already shown, and progress that goes
 * backwards is worse than progress that arrives a moment late. Nothing is lost:
 * `finish()` writes the newline that delimits the final redraw. And real stderr
 * (a traceback, a "not tracked by git" message) shares the stream, so anything
 * that isn't a progress line is handed back as `noise` for the error path.
 */

const ANSI = /\x1B\[[0-9;]*[A-Za-z]/g;
/** `[2/3] Running 37 gates …` — the stage counter every redraw starts with. */
const STAGE = /^\[(\d+)\/(\d+)\]\s+(.*)$/;
/** `Running 37 gates  [███░░░] 12/37 semgrep` — the gate bar, when present. */
const BAR = /^(.*?)\s*\[[█░]+\]\s*(\d+)\/(\d+)\s*(.*)$/;

export interface ScanProgress {
  /** Stage label, e.g. "Resolving scope", "Running 37 gates". */
  stage: string;
  stageIndex: number;
  stageTotal: number;
  /** Gates finished, and the total — both 0 outside the gate-running stage. */
  gatesDone: number;
  gatesTotal: number;
  /** The gate that just finished. */
  gate: string;
  /** 0..100. Stages are equal slices; the gate stage fills by gates completed. */
  percent: number;
}

function parseLine(raw: string): ScanProgress | undefined {
  const line = raw.replace(ANSI, '').trimEnd();
  const stage = STAGE.exec(line);
  if (!stage) return undefined;

  const stageIndex = Number(stage[1]);
  const stageTotal = Number(stage[2]);
  if (!stageTotal) return undefined;

  let label = stage[3];
  let gatesDone = 0;
  let gatesTotal = 0;
  let gate = '';
  const bar = BAR.exec(label);
  if (bar) {
    label = bar[1].trim();
    gatesDone = Number(bar[2]);
    gatesTotal = Number(bar[3]);
    gate = bar[4].trim();
  }

  // A stage counter of [2/3] means stage 2 has *started*, so 1 of 3 is behind
  // us. Within the gate stage — which is essentially the whole runtime — the
  // completed-gate fraction fills the slice.
  const withinStage = gatesTotal ? gatesDone / gatesTotal : 0;
  const percent = Math.min(100, Math.max(0, ((stageIndex - 1 + withinStage) / stageTotal) * 100));

  return { stage: label, stageIndex, stageTotal, gatesDone, gatesTotal, gate, percent };
}

function same(a: ScanProgress | undefined, b: ScanProgress): boolean {
  return (
    a !== undefined &&
    a.stage === b.stage &&
    a.stageIndex === b.stageIndex &&
    a.gatesDone === b.gatesDone &&
    a.gate === b.gate
  );
}

export class ProgressParser {
  private tail = '';
  private last: ScanProgress | undefined;

  /**
   * Feed a chunk of stderr. Returns the newest progress state when it changed,
   * plus any non-progress text seen in this chunk. Chunk boundaries do not
   * matter: only delimited segments are parsed.
   */
  feed(chunk: string): { progress?: ScanProgress; noise: string } {
    const segments = (this.tail + chunk).split(/[\r\n]/);
    this.tail = segments.pop() ?? ''; // No delimiter yet — wait for the rest.

    let progress: ScanProgress | undefined;
    const noise: string[] = [];
    for (const segment of segments) {
      if (!segment.trim()) continue;
      const parsed = parseLine(segment);
      if (parsed) progress = parsed;
      else noise.push(segment.replace(ANSI, ''));
    }

    if (progress && same(this.last, progress)) progress = undefined;
    if (progress) this.last = progress;
    return { progress, noise: noise.length ? noise.join('\n') + '\n' : '' };
  }

  /** Any trailing text left unterminated when the process exited. */
  flush(): string {
    const rest = this.tail;
    this.tail = '';
    return rest.trim() && !parseLine(rest) ? rest.replace(ANSI, '') + '\n' : '';
  }
}

/** "gates 12/37 · semgrep", or the stage label outside the gate stage. */
export function describeProgress(p: ScanProgress): string {
  if (!p.gatesTotal) return p.stage;
  const of = `gates ${p.gatesDone}/${p.gatesTotal}`;
  return p.gate ? `${of} · ${p.gate}` : of;
}

/** Status-bar sized: "12/37" while gates run, else a percentage. */
export function shortProgress(p: ScanProgress): string {
  return p.gatesTotal ? `${p.gatesDone}/${p.gatesTotal}` : `${Math.round(p.percent)}%`;
}
