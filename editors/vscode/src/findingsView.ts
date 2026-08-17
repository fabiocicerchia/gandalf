/**
 * The bottom pane: a plain VS Code tree view.
 *
 * Everything here is native — tree items with per-level icons, the view title
 * bar for the filters, the view badge for the error count, the view message for
 * the verdict and the "these gates could not run" notice. That buys type-ahead
 * filtering, keyboard navigation, theming and accessibility for free, and keeps
 * the pane looking like the Problems panel next to it rather than like a web
 * page embedded in an editor.
 */
import * as path from 'path';
import * as vscode from 'vscode';

import { gatesByStatus, LEVEL_LABEL, LEVELS, SEVERITY_LABEL } from './parse';
import { ResultStore } from './store';
import { Finding, Level, Outcome, Severity } from './types';

type ScopeFilter = 'file' | 'project';

interface FileNode {
  kind: 'file';
  id: string;
  label: string;
  uri?: vscode.Uri;
  children: FindingNode[];
}

interface FindingNode {
  kind: 'finding';
  id: string;
  finding: Finding;
}

export type Node = FileNode | FindingNode;

const WORD: Record<Outcome, string> = { pass: 'GREEN', warn: 'AMBER', fail: 'RED' };

/**
 * A distinct glyph per reported level, so the ladder is readable at a glance
 * instead of collapsing into three editor severities. Unrated findings fall back
 * to their gate's outcome — that is genuinely all that is known about them.
 */
const LEVEL_ICONS: Record<Exclude<Level, 'unrated'>, { id: string; color: string }> = {
  critical: { id: 'flame', color: 'charts.red' },
  high: { id: 'error', color: 'problemsErrorIcon.foreground' },
  medium: { id: 'warning', color: 'problemsWarningIcon.foreground' },
  low: { id: 'info', color: 'problemsInfoIcon.foreground' },
  info: { id: 'circle-outline', color: 'descriptionForeground' },
};

const UNRATED_ICONS: Record<Severity, { id: string; color: string }> = {
  error: { id: 'circle-filled', color: 'problemsErrorIcon.foreground' },
  warning: { id: 'circle-filled', color: 'problemsWarningIcon.foreground' },
  info: { id: 'circle-outline', color: 'descriptionForeground' },
};

function iconFor(f: Finding): vscode.ThemeIcon {
  const icon = f.level === 'unrated' ? UNRATED_ICONS[f.severity] : LEVEL_ICONS[f.level];
  return new vscode.ThemeIcon(icon.id, new vscode.ThemeColor(icon.color));
}

interface Model {
  roots: Node[];
  parents: Map<string, Node | undefined>;
}

export class FindingsView implements vscode.TreeDataProvider<Node> {
  static readonly viewId = 'gandalf.findings';

  private view?: vscode.TreeView<Node>;
  private scope: ScopeFilter = 'project';
  private levels = new Set<Level>(LEVELS);
  private severities = new Set<Severity>(['error', 'warning', 'info']);
  private scanLabel = '';
  /**
   * Bumped by Expand All. Tree item ids carry it, so a bump makes every node
   * new to the editor, which then applies our Expanded collapsible state instead
   * of the collapse it had remembered. Stable otherwise, so a node the user
   * collapsed by hand stays collapsed across refreshes and rescans.
   */
  private expansion = 0;
  private model?: Model;

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

  expandAll(): void {
    this.expansion += 1;
    this.refresh();
  }

  /**
   * One native multi-select quick pick over both axes: the level the tool
   * reported, and the editor severity it maps to. They are separate questions —
   * "show me the HIGHs" and "show me what squiggles as an error" — and a
   * finding has to pass both.
   */
  async pickFilters(): Promise<void> {
    const findings = this.all();
    const countLevel = (l: Level) => findings.filter((f) => f.level === l).length;
    const countSeverity = (s: Severity) => findings.filter((f) => f.severity === s).length;

    type Item = vscode.QuickPickItem & { level?: Level; severity?: Severity };
    const items: Item[] = [
      { label: 'Reported level', kind: vscode.QuickPickItemKind.Separator },
      ...LEVELS.map((l) => ({
        label: LEVEL_LABEL[l],
        description: `${countLevel(l)}`,
        detail: l === 'unrated' ? 'Findings whose tool reported no severity' : undefined,
        picked: this.levels.has(l),
        level: l,
      })),
      { label: 'Editor severity', kind: vscode.QuickPickItemKind.Separator },
      ...(['error', 'warning', 'info'] as Severity[]).map((s) => ({
        label: SEVERITY_LABEL[s],
        description: `${countSeverity(s)}`,
        picked: this.severities.has(s),
        severity: s,
      })),
    ];

    const chosen = await vscode.window.showQuickPick(items, {
      canPickMany: true,
      title: 'Gandalf: show which findings',
      placeHolder: 'A finding has to match a selected level and a selected severity',
    });
    if (!chosen) return;

    const levels = new Set(chosen.filter((c) => c.level).map((c) => c.level as Level));
    const severities = new Set(chosen.filter((c) => c.severity).map((c) => c.severity as Severity));
    // Clearing a whole axis would empty the pane with no way back from the
    // pane itself, so an empty axis means "all of it".
    this.levels = levels.size ? levels : new Set(LEVELS);
    this.severities = severities.size ? severities : new Set<Severity>(['error', 'warning', 'info']);
    this.refresh();
  }

  private get filtered(): boolean {
    return this.levels.size < LEVELS.length || this.severities.size < 3;
  }

  setScanning(label: string): void {
    this.scanLabel = label;
    this.refresh();
  }

  refresh(): void {
    this.model = undefined;
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

  /** Everything in scope, before the level/severity filters. */
  private all(): Finding[] {
    const folder = this.folder();
    if (!folder) return [];
    const all = this.store.findings(folder);
    if (this.scope !== 'file') return all;
    const active = vscode.window.activeTextEditor?.document.uri;
    if (!active || active.scheme !== 'file') return [];
    return all.filter((f) => f.resolvedPath === active.fsPath);
  }

  private visible(): Finding[] {
    return this.all().filter((f) => this.levels.has(f.level) && this.severities.has(f.severity));
  }

  /**
   * Built once per refresh. Rebuilding it inside getChildren — which the editor
   * calls once per node — made a scan O(files²).
   */
  private build(): Model {
    const parents = new Map<string, Node | undefined>();
    const findings = this.visible();
    const rev = this.expansion;

    if (this.scope === 'file') {
      const roots: Node[] = findings.map((f) => ({
        kind: 'finding',
        id: `${rev}:finding:${f.id}`,
        finding: f,
      }));
      for (const r of roots) parents.set(r.id, undefined);
      return { roots, parents };
    }

    const root = this.folder()?.uri.fsPath ?? '';
    const groups = new Map<string, FileNode>();
    for (const f of findings) {
      const key = f.resolvedPath || '';
      let node = groups.get(key);
      if (!node) {
        node = {
          kind: 'file',
          id: `${rev}:file:${key}`,
          label: key ? path.relative(root, key) : 'Project-level (no file)',
          uri: key ? vscode.Uri.file(key) : undefined,
          children: [],
        };
        groups.set(key, node);
      }
      const child: FindingNode = {
        kind: 'finding',
        id: `${rev}:finding:${node.children.length}:${f.id}`,
        finding: f,
      };
      node.children.push(child);
      parents.set(child.id, node);
    }

    const roots = [...groups.values()].sort((a, b) => {
      // Findings with nowhere to point sort last; everything else alphabetically.
      if (!a.uri !== !b.uri) return a.uri ? -1 : 1;
      return a.label.localeCompare(b.label);
    });
    for (const r of roots) parents.set(r.id, undefined);
    return { roots, parents };
  }

  private get tree(): Model {
    if (!this.model) this.model = this.build();
    return this.model;
  }

  getChildren(element?: Node): Node[] {
    if (!element) return this.tree.roots;
    return element.kind === 'file' ? element.children : [];
  }

  getParent(element: Node): Node | undefined {
    return this.tree.parents.get(element.id);
  }

  getTreeItem(node: Node): vscode.TreeItem {
    if (node.kind === 'file') {
      const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.Expanded);
      item.id = node.id;
      item.resourceUri = node.uri;
      item.iconPath = node.uri ? vscode.ThemeIcon.File : new vscode.ThemeIcon('project');
      item.description = `${node.children.length}`;
      item.contextValue = 'gandalfFile';
      item.tooltip = node.uri?.fsPath ?? 'Findings that are not tied to a file';
      return item;
    }

    const f = node.finding;
    const item = new vscode.TreeItem(f.message.split('\n')[0], vscode.TreeItemCollapsibleState.None);
    item.id = node.id;
    item.iconPath = iconFor(f);
    item.description = [f.severityLabel, f.gate, f.rule, f.line ? `line ${f.line}` : '']
      .filter(Boolean)
      .join(' · ');
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
    facts.push(`**level** ${f.severityLabel || LEVEL_LABEL[f.level].toLowerCase()}`);
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

    const state = run ? `${WORD[run.verdict]} · ${run.score}/100 · ${run.scope}` : undefined;
    view.description = this.scanLabel
      ? `scanning ${this.scanLabel}…`
      : [state, this.filtered ? 'filtered' : ''].filter(Boolean).join(' · ') || undefined;

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
      const hidden = this.all().length;
      lines.push(
        hidden > 0
          ? `${hidden} finding(s) hidden by the current filter — “Gandalf: Filter Findings”.`
          : this.scope === 'file'
            ? 'No findings in this file.'
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
