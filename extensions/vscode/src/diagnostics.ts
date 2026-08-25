/**
 * Findings → editor squiggles. The hover text is the diagnostic message, so it
 * carries the whole explanation: what the tool said, which gate found it, how
 * bad it is, and the rule id (linked to its docs when the tool ships a URL).
 */
import * as vscode from 'vscode';

import { Settings } from './config';
import { SEVERITY_RANK } from './parse';
import { Finding, Severity } from './types';

const VSCODE_SEVERITY: Record<Severity, vscode.DiagnosticSeverity> = {
  error: vscode.DiagnosticSeverity.Error,
  warning: vscode.DiagnosticSeverity.Warning,
  info: vscode.DiagnosticSeverity.Information,
};

export function describe(f: Finding): string {
  const facts = [`gate: ${f.gate}`, `category: ${f.category}`];
  if (f.severityLabel) facts.push(`severity: ${f.severityLabel}`);
  if (f.rule) facts.push(`rule: ${f.rule}`);
  return `${f.message}\n\n${facts.join(' · ')}`;
}

function toDiagnostic(f: Finding): vscode.Diagnostic {
  const line = Math.max(0, f.line - 1);
  const column = Math.max(0, f.column - 1);
  // End-of-line is clamped by the editor, so we get the whole line without
  // having to open the document to measure it.
  const range = new vscode.Range(line, column, line, Number.MAX_SAFE_INTEGER);
  const d = new vscode.Diagnostic(range, describe(f), VSCODE_SEVERITY[f.severity]);
  d.source = 'gandalf';
  if (f.rule) {
    d.code = f.url ? { value: f.rule, target: vscode.Uri.parse(f.url) } : f.rule;
  }
  return d;
}

/** One workspace folder's findings, with the settings that folder resolves to. */
export interface DiagnosticGroup {
  findings: Finding[];
  settings: Settings;
}

/** Backstop against a pathological file, not something worth configuring. */
const MAX_PER_FILE = 500;

export class DiagnosticPublisher {
  private readonly collection = vscode.languages.createDiagnosticCollection('gandalf');

  /**
   * Republishes everything at once. A partial publish is not an option: the
   * collection is global, so writing only the folder that was just scanned
   * would drop the other folders' diagnostics in a multi-root workspace.
   */
  publish(groups: DiagnosticGroup[]): void {
    this.collection.clear();
    const byFile = new Map<string, vscode.Diagnostic[]>();
    for (const { findings, settings } of groups) {
      if (!settings.diagnosticsEnabled) continue;
      const floor = SEVERITY_RANK[settings.minSeverity];
      for (const f of findings) {
        if (!f.resolvedPath || !f.line) continue; // No place to put it — the panel has it.
        if (SEVERITY_RANK[f.severity] > floor) continue;
        let list = byFile.get(f.resolvedPath);
        if (!list) byFile.set(f.resolvedPath, (list = []));
        if (list.length >= MAX_PER_FILE) continue;
        list.push(toDiagnostic(f));
      }
    }
    // One call, not one per file: each `set` crosses to the renderer, and a
    // tree with findings in a thousand files paid that a thousand times.
    const entries: [vscode.Uri, vscode.Diagnostic[]][] = [];
    for (const [file, diagnostics] of byFile) entries.push([vscode.Uri.file(file), diagnostics]);
    this.collection.set(entries);
  }

  clear(): void {
    this.collection.clear();
  }

  dispose(): void {
    this.collection.dispose();
  }
}
