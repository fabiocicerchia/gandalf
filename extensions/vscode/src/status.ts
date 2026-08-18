import * as vscode from 'vscode';

import { VERDICT_WORD } from './parse';
import { describeProgress, ScanProgress, shortProgress } from './progress';
import { LastRun } from './store';

export class StatusBar {
  private readonly item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 40);

  constructor() {
    this.item.command = 'gandalf.showReport';
    this.item.name = 'Gandalf';
  }

  scanning(label: string, p?: ScanProgress): void {
    this.item.text = p ? `$(sync~spin) Gandalf ${shortProgress(p)}` : '$(sync~spin) Gandalf';
    this.item.tooltip = p
      ? `Scanning ${label}\n${p.stage} — ${describeProgress(p)} (${Math.round(p.percent)}%)`
      : `Scanning ${label}…`;
    this.item.backgroundColor = undefined;
    this.item.show();
  }

  idle(run: LastRun | undefined, findings: number): void {
    if (!run) {
      this.item.text = '$(shield) Gandalf';
      this.item.tooltip = 'No scan yet — click to open the report, or run “Gandalf: Scan Workspace”.';
      this.item.backgroundColor = undefined;
      this.item.show();
      return;
    }
    const icon = run.verdict === 'pass' ? 'pass' : run.verdict === 'warn' ? 'warning' : 'error';
    this.item.text = `$(${icon}) Gandalf ${run.score}/100`;
    this.item.tooltip = new vscode.MarkdownString(
      [
        `**${VERDICT_WORD[run.verdict]} · ${run.score}/100**`,
        '',
        `Scope: \`${run.scope}\``,
        `Findings: ${findings}`,
        `Took ${(run.durationMs / 1000).toFixed(1)}s`,
        '',
        'Click to open the report.',
      ].join('\n'),
    );
    this.item.backgroundColor =
      run.verdict === 'fail'
        ? new vscode.ThemeColor('statusBarItem.errorBackground')
        : run.verdict === 'warn'
          ? new vscode.ThemeColor('statusBarItem.warningBackground')
          : undefined;
    this.item.show();
  }

  dispose(): void {
    this.item.dispose();
  }
}
