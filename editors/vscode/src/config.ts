import * as vscode from 'vscode';

import { Severity } from './types';

export type Trigger = 'onSave' | 'onSaveAndInterval' | 'interval' | 'manual';
export type SaveScope = 'file' | 'staged' | 'workspace';

export interface Settings {
  executable: string;
  checkoutPath: string;
  pythonPath: string;
  configPath: string;
  extraArgs: string[];
  trigger: Trigger;
  scopeOnSave: SaveScope;
  debounceMs: number;
  idleMs: number;
  intervalMinutes: number;
  scanOnStartup: boolean;
  timeoutSeconds: number;
  concurrency: number;
  useCache: boolean;
  cachePath: string;
  llm: boolean;
  diagnosticsEnabled: boolean;
  minSeverity: Severity;
  maxPerFile: number;
  reportsDirectory: string;
  reportsKeep: number;
  recordTrend: boolean;
  toolsImage: string;
  statusBarEnabled: boolean;
}

export function readSettings(scope?: vscode.Uri): Settings {
  const c = vscode.workspace.getConfiguration('gandalf', scope ?? null);
  const get = <T>(key: string, fallback: T): T => c.get<T>(key) ?? fallback;
  return {
    executable: get('executable', '').trim(),
    checkoutPath: get('checkoutPath', '').trim(),
    pythonPath: get('pythonPath', 'python3').trim() || 'python3',
    configPath: get('configPath', '').trim(),
    extraArgs: get<string[]>('extraArgs', []),
    trigger: get<Trigger>('scan.trigger', 'onSave'),
    scopeOnSave: get<SaveScope>('scan.scopeOnSave', 'file'),
    debounceMs: Math.max(250, get('scan.debounceMs', 1500)),
    idleMs: Math.max(0, get('scan.idleMs', 0)),
    intervalMinutes: Math.max(5, get('scan.intervalMinutes', 15)),
    scanOnStartup: get('scan.onStartup', true),
    timeoutSeconds: Math.max(10, get('scan.timeoutSeconds', 600)),
    concurrency: Math.max(0, get('scan.concurrency', 0)),
    useCache: get('scan.useCache', true),
    cachePath: get('scan.cachePath', '.gandalf-cache.json').trim(),
    llm: get('scan.llm', false),
    diagnosticsEnabled: get('diagnostics.enabled', true),
    minSeverity: get<Severity>('diagnostics.minSeverity', 'info'),
    maxPerFile: Math.max(1, get('diagnostics.maxPerFile', 500)),
    reportsDirectory: get('reports.directory', '').trim(),
    reportsKeep: Math.max(1, get('reports.keep', 8)),
    recordTrend: get('reports.recordTrend', false),
    toolsImage: get('tools.image', 'gandalf-tools').trim() || 'gandalf-tools',
    statusBarEnabled: get('statusBar.enabled', true),
  };
}
