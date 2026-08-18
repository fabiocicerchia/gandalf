import * as vscode from 'vscode';

let channel: vscode.LogOutputChannel | undefined;

export function log(): vscode.LogOutputChannel {
  if (!channel) channel = vscode.window.createOutputChannel('Gandalf', { log: true });
  return channel;
}

export function disposeLog(): void {
  channel?.dispose();
  channel = undefined;
}
