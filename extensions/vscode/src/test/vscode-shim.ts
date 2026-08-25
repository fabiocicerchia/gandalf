/**
 * Enough of the `vscode` API to run the store, the findings pane and the
 * diagnostic publisher under `node --test`.
 *
 * The alternative is @vscode/test-electron, which downloads and boots a whole
 * editor — worth it for testing UI, overkill for testing a merge, a memo and
 * how many times each of them walks the board. esbuild aliases `vscode` to this
 * when building the test bundle.
 *
 * Deliberately dumb: every stub records or returns, none of them think. A shim
 * that starts having behaviour of its own stops telling you anything about the
 * code under test.
 */
export class EventEmitter<T> {
  private handlers: ((e: T) => void)[] = [];

  event = (handler: (e: T) => void): { dispose: () => void } => {
    this.handlers.push(handler);
    return { dispose: () => (this.handlers = this.handlers.filter((h) => h !== handler)) };
  };

  fire(e: T): void {
    for (const handler of [...this.handlers]) handler(e);
  }

  dispose(): void {
    this.handlers = [];
  }
}

export const Uri = {
  file: (p: string) => ({ fsPath: p, toString: () => `file://${p}` }),
  parse: (s: string) => ({ fsPath: s, toString: () => s }),
};

export const workspace = {
  workspaceFolders: [] as { uri: { fsPath: string; toString(): string }; name: string }[],
  getWorkspaceFolder: (_uri: unknown): unknown => undefined,
};

// --- the findings pane -------------------------------------------------------

export enum TreeItemCollapsibleState {
  None = 0,
  Collapsed = 1,
  Expanded = 2,
}

export enum QuickPickItemKind {
  Separator = -1,
  Default = 0,
}

export class ThemeIcon {
  static readonly File = new ThemeIcon('file');
  constructor(
    readonly id: string,
    readonly color?: unknown,
  ) {}
}

export class ThemeColor {
  constructor(readonly id: string) {}
}

export class MarkdownString {
  value = '';
  appendMarkdown(md: string): this {
    this.value += md;
    return this;
  }
}

export class TreeItem {
  id?: string;
  iconPath?: unknown;
  resourceUri?: unknown;
  description?: string;
  tooltip?: unknown;
  contextValue?: string;
  command?: unknown;
  constructor(
    readonly label: string,
    readonly collapsibleState?: TreeItemCollapsibleState,
  ) {}
}

export class Range {
  constructor(
    readonly startLine: number,
    readonly startCharacter: number,
    readonly endLine?: number,
    readonly endCharacter?: number,
  ) {}
}

/** What `createTreeView` handed back, so a test can read the chrome it painted. */
export interface FakeTreeView {
  description?: string;
  badge?: { value: number; tooltip: string };
  message?: string;
  dispose(): void;
}

/** The quick pick's answer for the next call, and what it was asked. */
export const quickPick = {
  answer: undefined as unknown,
  lastItems: [] as unknown[],
};

export const window = {
  activeTextEditor: undefined as { document: { uri: { fsPath: string; scheme: string } } } | undefined,
  createTreeView: (_id: string, _opts: unknown): FakeTreeView => ({ dispose: () => undefined }),
  showQuickPick: (items: unknown[], _opts?: unknown): Promise<unknown> => {
    quickPick.lastItems = items;
    return Promise.resolve(quickPick.answer);
  },
};

export const commands = {
  executeCommand: (..._args: unknown[]): Promise<undefined> => Promise.resolve(undefined),
};

// --- diagnostics -------------------------------------------------------------

export enum DiagnosticSeverity {
  Error = 0,
  Warning = 1,
  Information = 2,
  Hint = 3,
}

export class Diagnostic {
  source?: string;
  code?: unknown;
  constructor(
    readonly range: Range,
    readonly message: string,
    readonly severity?: DiagnosticSeverity,
  ) {}
}

/**
 * Counts its writes. `set` crossing to the renderer is the cost the publisher
 * exists to keep down, so the count is the thing worth asserting on.
 */
export class FakeDiagnosticCollection {
  readonly entries = new Map<string, Diagnostic[]>();
  setCalls = 0;
  clearCalls = 0;

  set(
    first: { toString(): string } | ReadonlyArray<[{ toString(): string }, Diagnostic[] | undefined]>,
    second?: Diagnostic[],
  ): void {
    this.setCalls += 1;
    const pairs = Array.isArray(first)
      ? (first as ReadonlyArray<[{ toString(): string }, Diagnostic[] | undefined]>)
      : ([[first, second]] as [{ toString(): string }, Diagnostic[] | undefined][]);
    for (const [uri, diags] of pairs) {
      if (diags === undefined) this.entries.delete(uri.toString());
      else this.entries.set(uri.toString(), diags);
    }
  }

  clear(): void {
    this.clearCalls += 1;
    this.entries.clear();
  }

  dispose(): void {
    this.entries.clear();
  }
}

/** The collection the publisher under test created, for the test to inspect. */
export const diagnosticCollections: FakeDiagnosticCollection[] = [];

export const languages = {
  createDiagnosticCollection: (_name: string): FakeDiagnosticCollection => {
    const c = new FakeDiagnosticCollection();
    diagnosticCollections.push(c);
    return c;
  },
};
