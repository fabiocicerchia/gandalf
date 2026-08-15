/**
 * The bottom pane: a plain VS Code tree view.
 *
 * Everything here is native — tree items with severity icons, the view title
 * bar for the filters, the view badge for the error count, the view message for
 * the verdict and the "these gates could not run" notice. That buys type-ahead
 * filtering, keyboard navigation, theming and accessibility for free, and keeps
 * the pane looking like the Problems panel next to it rather than like a
 * web page embedded in an editor.
 */
import * as path from 'path';
import * as vscode from 'vscode';

import { gatesByStatus } from './parse';
import { ResultStore } from './store';
import { Finding, Outcome, Severity } from './types';

type ScopeFilter = 'file' | 'project';

interface FileNode {
  kind: 'file';
  label: string;
  uri?: vscode.Uri;
  findings: Finding[];
}

interface FindingNode {
  kind: 'finding';
  finding: Finding;
}

export type Node = FileNode | FindingNode;

const WORD: Record<Outcome, string> = { pass: 'GREEN', warn: 'AMBER', fail: 'RED' };

const ICONS: Record<Severity, { id: string; color: string }> = {
  error: { id: 'error', color: 'problemsErrorIcon.foreground' },
  warning: { id: 'warning', color: 'problemsWarningIcon.foreground' },
  info: { id: 'info', color: 'problemsInfoIcon.foreground' },
};

const SEVERITY_LABEL: Record<Severity, string> = {
  error: 'Errors',
  warning: 'Warnings',
  info: 'Info',
};

export class FindingsView implements vscode.TreeDataProvider<Node> {
  static readonly viewId = 'gandalf.findings';

  private view?: vscode.TreeView<Node>;
  private scope: ScopeFilter = 'project';
  private severities = new Set<Severity>(['error', 'warning', 'info']);
  private scanLabel = '';

  private readonly changed = new vscode.EventEmitter<Node | undefined>();
  readonly onDidChangeTreeData = this.changed.event;

  constructor(private readonly store: ResultStore) {}

  register(): vscode.Disposable {
    this.view = vscode.window.createTreeView(FindingsView.viewId, {
      treeDataProvider: this,
      showCollapseAll: true,
    });
    void vscode.commands.executeCommand('setContext', 'gandalf.scope', this.scope);
    this.refresh();
    return this.view;
  }

  setScope(scope: ScopeFilter): void {
    this.scope = scope;
    void vscode.commands.executeCommand('setContext', 'gandalf.scope', scope);
    this.refresh();
  }

  /** Native multi-select quick pick — no custom filter widgets. */
  async pickSeverities(): Promise<void> {
    const items = (['error', 'warning', 'info'] as Severity[]).map((s) => ({
      label: SEVERITY_LABEL[s],
      severity: s,
      picked: this.severities.has(s),
    }));
    const chosen = await vscode.window.showQuickPick(items, {
      canPickMany: true,
      title: 'Gandalf: severities to show',
    });
    if (!chosen) return;
    this.severities = new Set(chosen.map((c) => c.severity));
    if (this.severities.size === 0) this.severities = new Set<Severity>(['error', 'warning', 'info']);
    this.refresh();
  }

  setScanning(label: string): void {
    this.scanLabel = label;
    this.refresh();
  }

  refresh(): void {
    this.changed.fire(undefined);
    this.paintChrome();
  }

  // --- data ------------------------------------------------------------------

  private folder(): vscode.WorkspaceFolder | undefined {
    const active = vscode.window.activeTextEditor?.document.uri;
    return (
      (active ? vscode.workspace.getWorkspaceFolder(active) : undefined) ??
      this.store.folders()[0] ??
      vscode.workspace.workspaceFolders?.[0]
    );
  }

  private visible(): Finding[] {
    const folder = this.folder();
    if (!folder) return [];
    const all = this.store.findings(folder).filter((f) => this.severities.has(f.severity));
    if (this.scope !== 'file') return all;
    const active = vscode.window.activeTextEditor?.document.uri;
    if (!active || active.scheme !== 'file') return [];
    return all.filter((f) => f.resolvedPath === active.fsPath);
  }

  getChildren(element?: Node): Node[] {
    const findings = this.visible();
    if (element?.kind === 'file') return element.findings.map((f) => ({ kind: 'finding', finding: f }));
    if (element) return [];
    // A single file's findings are a flat list; the project view groups by file.
    if (this.scope === 'file') return findings.map((f) => ({ kind: 'finding', finding: f }));

    const folder = this.folder();
    const root = folder?.uri.fsPath ?? '';
    const groups = new Map<string, FileNode>();
    for (const f of findings) {
      const key = f.resolvedPath || '';
      let node = groups.get(key);
      if (!node) {
        node = {
          kind: 'file',
          label: key ? path.relative(root, key) : 'Project-level (no file)',
          uri: key ? vscode.Uri.file(key) : undefined,
          findings: [],
        };
        groups.set(key, node);
      }
      node.findings.push(f);
    }
    return [...groups.values()].sort((a, b) => {
      // Findings with nowhere to point sort last; everything else alphabetically.
      if (!a.uri !== !b.uri) return a.uri ? -1 : 1;
      return a.label.localeCompare(b.label);
    });
  }

  getTreeItem(node: Node): vscode.TreeItem {
    if (node.kind === 'file') {
      const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.Expanded);
      item.resourceUri = node.uri;
      item.iconPath = node.uri ? vscode.ThemeIcon.File : new vscode.ThemeIcon('project');
      item.description = `${node.findings.length}`;
      item.contextValue = 'gandalfFile';
      item.tooltip = node.uri?.fsPath ?? 'Findings that are not tied to a file';
      return item;
    }

    const f = node.finding;
    const item = new vscode.TreeItem(f.message.split('\n')[0], vscode.TreeItemCollapsibleState.None);
    const icon = ICONS[f.severity];
    item.iconPath = new vscode.ThemeIcon(icon.id, new vscode.ThemeColor(icon.color));
    item.description = [f.gate, f.rule, f.line ? `line ${f.line}` : ''].filter(Boolean).join(' · ');
    item.tooltip = this.tooltip(f);
    item.contextValue = 'gandalfFinding';
    if (f.resolvedPath) {
      item.resourceUri = vscode.Uri.file(f.resolvedPath);
      item.command = {
        command: 'vscode.open',
        title: 'Open',
        arguments: [
          vscode.Uri.file(f.resolvedPath),
          {
            selection: new vscode.Range(
              Math.max(0, f.line - 1),
              Math.max(0, f.column - 1),
              Math.max(0, f.line - 1),
              Math.max(0, f.column - 1),
            ),
          } satisfies vscode.TextDocumentShowOptions,
        ],
      };
    }
    return item;
  }

  private tooltip(f: Finding): vscode.MarkdownString {
    const md = new vscode.MarkdownString();
    md.appendMarkdown(`${f.message}\n\n`);
    const facts = [`**gate** ${f.gate}`, `**category** ${f.category}`];
    if (f.severityLabel) facts.push(`**severity** ${f.severityLabel}`);
    if (f.rule) facts.push(`**rule** \`${f.rule}\``);
    md.appendMarkdown(facts.join(' · '));
    if (f.url) md.appendMarkdown(`\n\n[Rule documentation](${f.url})`);
    return md;
  }

  // --- title bar / message / badge -------------------------------------------

  private paintChrome(): void {
    const view = this.view;
    if (!view) return;
    const folder = this.folder();
    const run = folder ? this.store.lastRun(folder) : undefined;
    const findings = this.visible();

    view.description = this.scanLabel
      ? `scanning ${this.scanLabel}…`
      : run
        ? `${WORD[run.verdict]} · ${run.score}/100 · ${run.scope}`
        : undefined;

    const errors = findings.filter((f) => f.severity === 'error').length;
    view.badge = errors ? { value: errors, tooltip: `${errors} error(s)` } : undefined;

    view.message = this.message(findings.length, Boolean(run));
  }

  private message(shown: number, scanned: boolean): string | undefined {
    const lines: string[] = [];
    const folder = this.folder();
    const snapshot = folder ? this.store.project(folder) : undefined;

    if (!scanned) {
      lines.push('Nothing scanned yet — run “Gandalf: Scan Workspace”.');
    } else if (shown === 0) {
      lines.push(
        this.scope === 'file'
          ? 'No findings in this file.'
          : this.severities.size < 3
            ? 'No findings at the selected severities.'
            : 'No findings — every gate that ran is green.',
      );
    }

    if (snapshot) {
      const { blocked, inapplicable } = gatesByStatus(snapshot.payload);
      if (blocked.length) {
        lines.push(
          `⚠ ${blocked.length} gate(s) could not run (${blocked.map((g) => g.name).join(', ')}) — run “Gandalf: Check Environment”.`,
        );
      }
      const quiet: string[] = [];
      if (inapplicable.length) quiet.push(`${inapplicable.length} had nothing to assess`);
      if (snapshot.payload.skipped_gates?.length) {
        quiet.push(`${snapshot.payload.skipped_gates.length} irrelevant to the languages in scope`);
      }
      if (snapshot.payload.disabled_gates?.length) {
        quiet.push(`${snapshot.payload.disabled_gates.length} disabled by config`);
      }
      if (quiet.length) lines.push(`Gates not counted: ${quiet.join(', ')}.`);
    }
    return lines.length ? lines.join('\n') : undefined;
  }

  dispose(): void {
    this.changed.dispose();
  }
}
