/**
 * Telling the user a scan failed, without telling them thirty times.
 *
 * A scan can fail on every save — a broken `gandalf.path`, an interpreter that
 * moved, a gate that will not start — and a popup per save is worse than the
 * failure. So the cooldown and the once-only "gandalf is not installed" notice
 * are state, and they live here with the decision that reads them.
 */
import * as vscode from 'vscode';

import { log } from './log';
import { GandalfNotFoundError, promptInstall, ScanSkippedError } from './runner';
import { Job, jobLabel } from './scheduler';

const ERROR_COOLDOWN_MS = 60_000;

export class FailureNotifier {
  private lastErrorAt = 0;
  private notFoundShown = false;

  /** A new configuration may have fixed it: offer the install notice again. */
  reset(): void {
    this.notFoundShown = false;
  }

  report(err: unknown, job: Job): void {
    if (err instanceof vscode.CancellationError) {
      log().info(`scan cancelled: ${jobLabel(job)}`);
      return;
    }
    if (err instanceof ScanSkippedError) {
      log().info(`scan skipped: ${err.message}`);
      return;
    }
    if (err instanceof GandalfNotFoundError) {
      this.reportMissing(err);
      return;
    }
    const message = err instanceof Error ? err.message : String(err);
    log().error(message);
    if (job.manual || Date.now() - this.lastErrorAt > ERROR_COOLDOWN_MS) {
      this.lastErrorAt = Date.now();
      void vscode.window.showErrorMessage(`Gandalf: ${message}`, 'Show log').then((choice) => {
        if (choice === 'Show log') log().show(true);
      });
    }
  }

  /** "gandalf is missing" is offered once, with the command that fixes it. */
  private reportMissing(err: GandalfNotFoundError): void {
    log().error(err.message);
    if (this.notFoundShown) return;
    this.notFoundShown = true;
    void promptInstall(err.message);
  }
}
