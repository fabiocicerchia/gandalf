/**
 * Enough of the `vscode` API for the store to run under `node --test`.
 *
 * The alternative is @vscode/test-electron, which downloads and boots a whole
 * editor — worth it for testing UI, overkill for testing a merge and a memo.
 * esbuild aliases `vscode` to this when building the test bundle.
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
};

export const workspace = {
  workspaceFolders: [] as { uri: { fsPath: string; toString(): string }; name: string }[],
};
