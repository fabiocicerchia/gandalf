/**
 * gandalf's `--stream` output: one NDJSON line per gate, as it finishes.
 *
 * Without it nothing reaches a consumer until the final report is written, so a
 * findings pane sits empty for the whole run. The aggregate still comes only
 * from the report — a verdict and a composite score are properties of the whole
 * run, and no single gate result can produce them.
 *
 * Event lines share stdout with the human scorecard, which is printed at the end;
 * they are picked out by their `{"event":` prefix and everything else is left
 * alone for the caller to read as before.
 */
import { Outcome, RawFinding, RawGate } from './types';

export interface StartEvent {
  event: 'start';
  scope: string;
  gates: number;
}

export interface GateEvent extends RawGate {
  event: 'gate';
  index: number;
  total: number;
}

export type StreamEvent = StartEvent | GateEvent;

const PREFIX = '{"event"';

function isOutcome(v: unknown): v is Outcome {
  return v === 'pass' || v === 'warn' || v === 'fail';
}

/** Validate rather than trust: a malformed line must not poison the pane. */
function toEvent(parsed: unknown): StreamEvent | undefined {
  if (!parsed || typeof parsed !== 'object') return undefined;
  const o = parsed as Record<string, unknown>;
  if (o.event === 'start') {
    return typeof o.gates === 'number'
      ? { event: 'start', scope: String(o.scope ?? ''), gates: o.gates }
      : undefined;
  }
  if (o.event !== 'gate') return undefined;
  if (typeof o.name !== 'string' || !isOutcome(o.outcome)) return undefined;
  return {
    event: 'gate',
    index: typeof o.index === 'number' ? o.index : 0,
    total: typeof o.total === 'number' ? o.total : 0,
    name: o.name,
    outcome: o.outcome,
    score: typeof o.score === 'number' ? o.score : 0,
    summary: typeof o.summary === 'string' ? o.summary : '',
    findings: Array.isArray(o.findings) ? (o.findings as RawFinding[]) : [],
    category: typeof o.category === 'string' ? o.category : undefined,
    blocking: o.blocking === true,
    duration: typeof o.duration === 'number' ? o.duration : null,
  };
}

export class EventParser {
  private tail = '';

  /** Feed a chunk of stdout; returns whatever complete events it contained. */
  feed(chunk: string): StreamEvent[] {
    const lines = (this.tail + chunk).split('\n');
    this.tail = lines.pop() ?? '';
    const events: StreamEvent[] = [];
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith(PREFIX)) continue;
      try {
        const event = toEvent(JSON.parse(trimmed));
        if (event) events.push(event);
      } catch {
        // A truncated or malformed line is not worth failing a scan over.
      }
    }
    return events;
  }
}
