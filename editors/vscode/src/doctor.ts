/**
 * "Which gates can actually run here?"
 *
 * gandalf degrades a gate to AMBER when its tool is missing, so a green board
 * can quietly mean "never checked". The doctor spells out what is present on
 * PATH, what the scanner-tools image would supply, and what is simply absent.
 *
 * The tool inventory mirrors `gandalf/plugins.py` (IMAGE_TOOLS) and the gates
 * that shell out to their own images (kics, codeql) or host toolchains.
 */
import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

import { Settings } from './config';
import { log } from './log';
import { findOnPath, GandalfNotFoundError, probe, resolveLauncher } from './runner';

/** Supplied by the gandalf-tools image when absent from PATH (plugins.IMAGE_TOOLS). */
const IMAGE_TOOLS = [
  'actionlint',
  'bandit',
  'checkov',
  'codespell',
  'gitleaks',
  'hadolint',
  'interrogate',
  'lizard',
  'mdl',
  'mypy',
  'osv-scanner',
  'pip-audit',
  'ruff',
  'scorecard',
  'semgrep',
  'shellcheck',
  'sqlfluff',
  'squawk',
  'trivy',
  'vulture',
  'yamllint',
];

/** Language toolchains gandalf never containerizes — they come from the host. */
const HOST_TOOLS = [
  'go',
  'golangci-lint',
  'govulncheck',
  'cargo',
  'cargo-audit',
  'node',
  'npm',
  'npx',
];

/** Gates that run their own image, so docker alone is enough. */
const DOCKER_GATES = ['kics', 'codeql', 'ci_act (act)'];

/** Only used with `--target`, so their absence is expected in an editor. */
const DYNAMIC_TOOLS = ['nikto', 'sqlmap', 'dalfox'];

interface Line {
  ok: boolean;
  text: string;
}

function section(title: string, lines: Line[]): string {
  const body = lines.map((l) => `  ${l.ok ? '✔' : '✖'} ${l.text}`).join('\n');
  return `${title}\n${body}`;
}

export async function runDoctor(folder: vscode.WorkspaceFolder, s: Settings): Promise<void> {
  const out = log();
  out.show(true);
  out.info('— Gandalf environment check —');

  const report: string[] = [];
  const problems: string[] = [];

  // 1. gandalf itself.
  let gandalfLine: Line;
  try {
    const launcher = await resolveLauncher(folder, s);
    const version = await probe(launcher.command, [...launcher.args, '--help'], folder.uri.fsPath);
    gandalfLine = { ok: version.ok, text: launcher.label };
    if (!version.ok) problems.push('gandalf could not be executed');
    const missingFlags = ['--out-dir', '--no-trend'].filter((f) => !launcher.flags.has(f));
    if (missingFlags.length) {
      report.push(
        `  ℹ this gandalf build has no ${missingFlags.join('/')} — reports will land in ` +
          `the repository's reports/ directory. Update the checkout to keep them out of the tree.`,
      );
    }
  } catch (err) {
    gandalfLine = { ok: false, text: err instanceof Error ? err.message : String(err) };
    problems.push('gandalf not found');
  }
  report.push(section('gandalf', [gandalfLine]));

  // 2. git — every scope starts from git state.
  const git = findOnPath('git');
  report.push(section('git', [{ ok: Boolean(git), text: git || 'not on PATH — gandalf cannot resolve a scope' }]));
  if (!git) problems.push('git not on PATH');

  const isRepo = fs.existsSync(path.join(folder.uri.fsPath, '.git'));
  report.push(
    section('workspace', [
      { ok: isRepo, text: isRepo ? `${folder.uri.fsPath} is a git repository` : `${folder.uri.fsPath} is not a git repository` },
    ]),
  );
  if (!isRepo) problems.push('workspace is not a git repository');

  // 3. docker + the scanner-tools image.
  const docker = findOnPath('docker');
  const imageCheck = docker
    ? await probe(docker, ['image', 'inspect', s.toolsImage], folder.uri.fsPath)
    : { ok: false, output: '' };
  report.push(
    section('docker', [
      { ok: Boolean(docker), text: docker || 'not on PATH — containerized gates will be skipped' },
      {
        ok: imageCheck.ok,
        text: imageCheck.ok
          ? `scanner-tools image "${s.toolsImage}" present`
          : `scanner-tools image "${s.toolsImage}" missing — run “Gandalf: Build Scanner Tools Image”`,
      },
      { ok: Boolean(docker), text: `image-backed gates: ${DOCKER_GATES.join(', ')}` },
    ]),
  );

  // 4. The scanner tools, by where they would come from.
  const onPath = new Map(IMAGE_TOOLS.concat(HOST_TOOLS, DYNAMIC_TOOLS).map((t) => [t, findOnPath(t)]));
  const fromImage: string[] = [];
  const missing: string[] = [];
  const imageLines = IMAGE_TOOLS.map((tool) => {
    const host = onPath.get(tool);
    if (host) return { ok: true, text: `${tool} — host` };
    if (imageCheck.ok) {
      fromImage.push(tool);
      return { ok: true, text: `${tool} — ${s.toolsImage}` };
    }
    missing.push(tool);
    return { ok: false, text: `${tool} — missing` };
  });
  report.push(section('scanner tools', imageLines));

  const hostLines = HOST_TOOLS.map((tool) => ({
    ok: Boolean(onPath.get(tool)),
    text: `${tool}${onPath.get(tool) ? '' : ' — missing (its gates will report AMBER "unavailable")'}`,
  }));
  report.push(section('language toolchains (host only)', hostLines));

  report.push(
    section(
      'dynamic scanners (only used with --target)',
      DYNAMIC_TOOLS.map((t) => ({ ok: Boolean(onPath.get(t)), text: t })),
    ),
  );

  // 5. The LLM endpoint. Always checked, not just when summaries are on: the
  // skill-backed gates call the model themselves, so an unreachable endpoint
  // costs every scan the retry backoff whatever the summary setting says.
  const url = (process.env.GANDALF_LLM_URL ?? 'http://127.0.0.1:8787/v1').replace(/\/$/, '');
  let llmOk = false;
  let llmDetail = '';
  try {
    const res = await fetch(`${url}/models`, { signal: AbortSignal.timeout(3000) });
    llmOk = res.ok;
    llmDetail = `HTTP ${res.status}`;
  } catch (err) {
    llmDetail = err instanceof Error ? err.message : String(err);
  }
  const llmLines: Line[] = [{ ok: llmOk, text: `${url} — ${llmDetail}` }];
  if (!llmOk) {
    llmLines.push({
      ok: s.llmRetries >= 0 && s.llmRetries <= 1,
      text:
        'the skill-backed judge gates (grill_me, well_architected, security_assessment, …) call ' +
        'this endpoint regardless of gandalf.scan.llm. Retry budget for editor scans: ' +
        (s.llmRetries < 0
          ? "gandalf's default of 3, which costs ~7s per call while the endpoint is down — " +
            'lower gandalf.scan.llmRetries to fail fast'
          : `${s.llmRetries} (gandalf.scan.llmRetries)`),
    });
  }
  report.push(section('LLM endpoint', llmLines));
  if (!llmOk && s.llm) problems.push('LLM endpoint unreachable (summaries will degrade to a note)');

  out.info('\n' + report.join('\n\n') + '\n');

  const summary = missing.length
    ? `${missing.length} scanner tool(s) unavailable: ${missing.slice(0, 6).join(', ')}${missing.length > 6 ? '…' : ''}`
    : `All scanner tools available (${fromImage.length} via ${s.toolsImage}).`;
  const headline = problems.length ? `${problems.join('; ')}. ${summary}` : summary;

  const actions: string[] = ['Show log'];
  if (!imageCheck.ok && docker) actions.push('Build tools image');
  const offerFastFail = !llmOk && s.llmRetries !== 0;
  if (offerFastFail) actions.push('Skip LLM retries');
  const choice = await (problems.length || missing.length || offerFastFail
    ? vscode.window.showWarningMessage(`Gandalf: ${headline}`, ...actions)
    : vscode.window.showInformationMessage(`Gandalf: ${headline}`, ...actions));
  if (choice === 'Build tools image') await vscode.commands.executeCommand('gandalf.buildToolsImage');
  if (choice === 'Skip LLM retries') {
    await vscode.workspace
      .getConfiguration('gandalf')
      .update('scan.llmRetries', 0, vscode.ConfigurationTarget.Workspace);
    void vscode.window.showInformationMessage(
      'Gandalf: judge gates will now fail fast instead of retrying an unreachable endpoint.',
    );
  }
  if (choice === 'Show log') out.show(true);
}

/**
 * Build the scanner-tools image in a terminal — it is a multi-minute,
 * output-heavy docker build, which belongs in a terminal the user can watch and
 * interrupt, not behind a progress spinner.
 */
export async function buildToolsImage(folder: vscode.WorkspaceFolder, s: Settings): Promise<void> {
  let checkout = '';
  try {
    checkout = (await resolveLauncher(folder, s)).checkout;
  } catch (err) {
    if (err instanceof GandalfNotFoundError) {
      void vscode.window.showErrorMessage(err.message);
      return;
    }
    throw err;
  }
  if (!checkout || !fs.existsSync(path.join(checkout, 'tools.Dockerfile'))) {
    void vscode.window.showErrorMessage(
      'Gandalf: the tools image is built from `tools.Dockerfile` in a gandalf checkout. ' +
        'Set `gandalf.checkoutPath` to one, then run this again.',
    );
    return;
  }
  const terminal = vscode.window.createTerminal({ name: 'gandalf: build tools', cwd: checkout });
  terminal.show(true);
  terminal.sendText(`docker build -f tools.Dockerfile -t ${s.toolsImage} .`);
}
