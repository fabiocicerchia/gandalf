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

export class CancellationError extends Error {}

export class CancellationTokenSource {
  private handlers: (() => void)[] = [];
  readonly token = {
    isCancellationRequested: false,
    onCancellationRequested: (h: () => void) => {
      this.handlers.push(h);
      return { dispose: () => undefined };
    },
  };

  cancel(): void {
    this.token.isCancellationRequested = true;
    for (const h of [...this.handlers]) h();
  }

  dispose(): void {
    this.handlers = [];
  }
}

/**
 * Configuration the extension will read, as `section -> key -> value`. A test
 * sets what it needs; everything else falls through to the code's own defaults.
 */
export const configuration: Record<string, Record<string, unknown>> = {};

/** Every listener the extension registered, by the API it registered against. */
export const listeners: Record<string, ((e: never) => unknown)[]> = {};

const listenerFor =
  (name: string) =>
  (handler: (e: never) => unknown): { dispose: () => void } => {
    (listeners[name] ??= []).push(handler);
    return {
      dispose: () => (listeners[name] = (listeners[name] ?? []).filter((h) => h !== handler)),
    };
  };

export const workspace = {
  workspaceFolders: [] as { uri: { fsPath: string; toString(): string }; name: string }[],
  getWorkspaceFolder: (_uri: unknown): unknown => undefined,
  getConfiguration: (section: string, _scope?: unknown) => ({
    get: <T>(key: string): T | undefined => configuration[section]?.[key] as T | undefined,
  }),
  onDidSaveTextDocument: listenerFor('onDidSaveTextDocument'),
  onDidChangeConfiguration: listenerFor('onDidChangeConfiguration'),
  onDidChangeWorkspaceFolders: listenerFor('onDidChangeWorkspaceFolders'),
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

// --- chrome the extension paints ---------------------------------------------

export enum StatusBarAlignment {
  Left = 1,
  Right = 2,
}

export enum ProgressLocation {
  SourceControl = 1,
  Window = 10,
  Notification = 15,
}

export enum ViewColumn {
  Active = -1,
}

/** Every modal the extension raised: what it said and what it offered. */
export const notifications: { kind: string; message: string; actions: string[] }[] = [];
/** The answer `showErrorMessage`/`showWarningMessage`/… returns next. */
export const notificationAnswer = { value: undefined as unknown };

const notify =
  (kind: string) =>
  (message: string, ...actions: unknown[]): Promise<unknown> => {
    notifications.push({ kind, message, actions: actions.map(String) });
    return Promise.resolve(notificationAnswer.value);
  };

/** Lines the extension logged, most recent last. */
export const logLines: string[] = [];

class FakeLogChannel {
  readonly name = 'Gandalf';
  private write = (level: string) => (message: string) => logLines.push(`${level} ${message}`);
  trace = this.write('trace');
  debug = this.write('debug');
  info = this.write('info');
  warn = this.write('warn');
  error = (e: string | Error) => logLines.push(`error ${e instanceof Error ? e.message : e}`);
  show(_preserveFocus?: boolean): void {
    logLines.push('show');
  }
  dispose(): void {
    logLines.length = 0;
  }
}

export class FakeStatusBarItem {
  text = '';
  tooltip: unknown;
  command: unknown;
  name = '';
  backgroundColor: unknown;
  shown = 0;
  disposed = 0;
  show(): void {
    this.shown += 1;
  }
  dispose(): void {
    this.disposed += 1;
  }
}

/** The status bar items, tree views and terminals the extension created. */
export const created = {
  statusBarItems: [] as FakeStatusBarItem[],
  treeViews: [] as string[],
  terminals: [] as { name: string; sent: string[] }[],
};

export const window = {
  activeTextEditor: undefined as { document: { uri: { fsPath: string; scheme: string } } } | undefined,
  state: { focused: true },
  createTreeView: (id: string, _opts: unknown): FakeTreeView => {
    created.treeViews.push(id);
    return { dispose: () => undefined };
  },
  showQuickPick: (items: unknown[], _opts?: unknown): Promise<unknown> => {
    quickPick.lastItems = items;
    return Promise.resolve(quickPick.answer);
  },
  createStatusBarItem: (_alignment?: StatusBarAlignment, _priority?: number): FakeStatusBarItem => {
    const item = new FakeStatusBarItem();
    created.statusBarItems.push(item);
    return item;
  },
  createOutputChannel: (_name: string, _opts?: unknown) => new FakeLogChannel(),
  createTerminal: (opts: string | { name: string }) => {
    const terminal = { name: typeof opts === 'string' ? opts : opts.name, sent: [] as string[] };
    created.terminals.push(terminal);
    return {
      show: (_preserveFocus?: boolean) => undefined,
      sendText: (text: string) => terminal.sent.push(text),
      dispose: () => undefined,
    };
  },
  createWebviewPanel: (_type: string, _title: string, _column: unknown, _opts: unknown) => {
    throw new Error('vscode-shim: no webview in these tests');
  },
  withProgress: <T>(
    _opts: unknown,
    task: (
      progress: { report(v: { message?: string; increment?: number }): void },
      token: CancellationTokenSource['token'],
    ) => Thenable<T>,
  ): Thenable<T> => task({ report: () => undefined }, new CancellationTokenSource().token),
  showErrorMessage: notify('error'),
  showWarningMessage: notify('warning'),
  showInformationMessage: notify('information'),
  showSaveDialog: (_opts: unknown): Promise<unknown> => Promise.resolve(undefined),
  onDidChangeActiveTextEditor: listenerFor('onDidChangeActiveTextEditor'),
};

/** Command id -> the handler activate() registered for it. */
export const registeredCommands = new Map<string, (...args: unknown[]) => unknown>();
/** Commands the extension asked the editor to run, with their arguments. */
export const executedCommands: { id: string; args: unknown[] }[] = [];

export const commands = {
  executeCommand: (id: string, ...args: unknown[]): Promise<undefined> => {
    executedCommands.push({ id, args });
    return Promise.resolve(undefined);
  },
  registerCommand: (id: string, handler: (...args: unknown[]) => unknown) => {
    registeredCommands.set(id, handler);
    return { dispose: () => registeredCommands.delete(id) };
  },
};

/** External URLs the extension asked the editor to open. */
export const openedExternal: string[] = [];

export const env = {
  openExternal: (uri: { toString(): string }): Promise<boolean> => {
    openedExternal.push(uri.toString());
    return Promise.resolve(true);
  },
  clipboard: {
    text: '',
    writeText: (text: string): Promise<void> => {
      env.clipboard.text = text;
      return Promise.resolve();
    },
  },
};

/** Put every recorder back to empty, so one test cannot read another's traffic. */
export function resetShim(): void {
  for (const key of Object.keys(configuration)) delete configuration[key];
  for (const key of Object.keys(listeners)) delete listeners[key];
  registeredCommands.clear();
  diagnosticCollections.length = 0;
  notifications.length = 0;
  executedCommands.length = 0;
  openedExternal.length = 0;
  logLines.length = 0;
  created.statusBarItems.length = 0;
  created.treeViews.length = 0;
  created.terminals.length = 0;
  notificationAnswer.value = undefined;
  quickPick.answer = undefined;
  quickPick.lastItems = [];
  workspace.workspaceFolders = [];
  window.activeTextEditor = undefined;
  env.clipboard.text = '';
}

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
