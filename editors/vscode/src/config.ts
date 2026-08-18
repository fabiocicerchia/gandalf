import * as vscode from 'vscode';

import { Severity } from './types';

export type Trigger = 'onSave' | 'onSaveAndInterval' | 'interval' | 'manual';

export interface Settings {
  /** A `gandalf` wrapper, or a source checkout. Empty means auto-detect. */
  path: string;
  pythonPath: string;
  configPath: string;
  extraArgs: string[];
  exclude: string[];
  useEditorExcludes: boolean;
  trigger: Trigger;
  debounceMs: number;
  intervalMinutes: number;
  scanOnStartup: boolean;
  timeoutSeconds: number;
  concurrency: number;
  useCache: boolean;
  llm: boolean;
  diagnosticsEnabled: boolean;
  minSeverity: Severity;
}

export function readSettings(scope?: vscode.Uri): Settings {
  const c = vscode.workspace.getConfiguration('gandalf', scope ?? null);
  const get = <T>(key: string, fallback: T): T => c.get<T>(key) ?? fallback;
  return {
    path: get('path', '').trim(),
    pythonPath: get('pythonPath', 'python3').trim() || 'python3',
    configPath: get('configPath', '').trim(),
    extraArgs: get<string[]>('extraArgs', []),
    exclude: get<string[]>('exclude', []),
    useEditorExcludes: get('useEditorExcludes', true),
    trigger: get<Trigger>('scan.trigger', 'onSave'),
    debounceMs: Math.max(250, get('scan.debounceMs', 1500)),
    intervalMinutes: Math.max(5, get('scan.intervalMinutes', 15)),
    scanOnStartup: get('scan.onStartup', true),
    timeoutSeconds: Math.max(10, get('scan.timeoutSeconds', 600)),
    concurrency: Math.max(0, get('scan.concurrency', 0)),
    useCache: get('scan.useCache', true),
    llm: get('scan.llm', false),
    diagnosticsEnabled: get('diagnostics.enabled', true),
    minSeverity: get<Severity>('diagnostics.minSeverity', 'info'),
  };
}
