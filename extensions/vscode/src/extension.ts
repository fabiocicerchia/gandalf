/**
 * The activation sequence, and nothing else.
 *
 * Three things happen when the window opens: a session is built, the commands
 * and the editor events are pointed at it, and the triggers are armed. Each is
 * one call, and everything either of them does lives in `session.ts` or
 * `commands.ts`.
 */
import * as vscode from 'vscode';

import { commandHandlers } from './commands';
import { disposeLog } from './log';
import { resetLauncherCache } from './runner';
import { Session } from './session';

function registerCommands(session: Session): vscode.Disposable[] {
  return Object.entries(commandHandlers(session)).map(([id, handler]) =>
    vscode.commands.registerCommand(id, handler),
  );
}

function registerListeners(session: Session): vscode.Disposable[] {
  return [
    vscode.window.onDidChangeActiveTextEditor(() => session.findingsView.refresh()),
    vscode.workspace.onDidSaveTextDocument((doc) => void session.onSave(doc)),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (!e.affectsConfiguration('gandalf')) return;
      // The launcher is cached per folder, and `gandalf.path` may have moved.
      session.reconfigure(resetLauncherCache);
    }),
    vscode.workspace.onDidChangeWorkspaceFolders(() => session.armSweep()),
  ];
}

export function activate(context: vscode.ExtensionContext): void {
  const session = new Session(context);
  context.subscriptions.push(
    ...session.disposables(),
    { dispose: disposeLog },
    ...registerCommands(session),
    ...registerListeners(session),
    ...session.start(),
  );
}

export function deactivate(): void {
  // Everything is registered in context.subscriptions.
}
