/**
 * The scorecard, shown exactly as gandalf renders it.
 *
 * gandalf already writes a self-contained HTML report (inline CSS + JS, no
 * network references), so the extension shows that file rather than
 * reimplementing the layout — the report in the editor and the report in CI are
 * literally the same document. Two small injections adapt it to a webview: a
 * CSP, and a bridge that seeds its light/dark toggle from the editor theme and
 * hands external links to the editor.
 */
import * as fs from 'fs';
import * as vscode from 'vscode';

const BRIDGE = `
(function(){
  var api = acquireVsCodeApi(), root = document.documentElement;
  function sync(){
    var dark = document.body.classList.contains('vscode-dark') ||
               document.body.classList.contains('vscode-high-contrast');
    // The report persists its own choice; only seed it when there isn't one.
    if(!localStorage.getItem('gandalf-theme')) root.dataset.theme = dark ? 'dark' : 'light';
  }
  new MutationObserver(sync).observe(document.body, {attributes:true, attributeFilter:['class']});
  sync();
  document.addEventListener('click', function(e){
    var a = e.target && e.target.closest && e.target.closest('a[href^="http"]');
    if(!a) return;
    e.preventDefault();
    api.postMessage({type:'open', href: a.getAttribute('href')});
  });
})();
`;

function adapt(html: string, webview: vscode.Webview): string {
  // The report's own <style>/<script> are inline and unversioned, so
  // 'unsafe-inline' is unavoidable; everything else stays denied.
  const csp =
    `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; ` +
    `style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src ${webview.cspSource} data:;">`;
  return html
    .replace('<meta charset="utf-8">', `<meta charset="utf-8">${csp}`)
    .replace('</body>', `<script>${BRIDGE}</script></body>`);
}

export class ReportView {
  private panel?: vscode.WebviewPanel;
  private lastPath = '';
  /** A newer report landed while the tab was hidden; it repaints on return. */
  private stale = false;

  /** Path of the most recent report, so "Open Report" works without rescanning. */
  get current(): string {
    return this.lastPath;
  }

  set current(p: string) {
    this.lastPath = p;
    if (!p || !this.panel) return;
    // `retainContextWhenHidden` keeps the tab alive, so a scan-on-save would
    // otherwise re-read and re-render a multi-megabyte document nobody is
    // looking at, on every save.
    if (this.panel.visible) void this.load(p);
    else this.stale = true;
  }

  async show(htmlPath: string, title: string): Promise<void> {
    this.lastPath = htmlPath;
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel(
        'gandalf.report',
        'Gandalf report',
        { viewColumn: vscode.ViewColumn.Active, preserveFocus: false },
        { enableScripts: true, enableFindWidget: true, retainContextWhenHidden: true },
      );
      this.panel.onDidDispose(() => (this.panel = undefined));
      this.panel.onDidChangeViewState(() => {
        if (this.panel?.visible && this.stale) void this.load(this.lastPath);
      });
      this.panel.webview.onDidReceiveMessage((msg: { type: string; href?: string }) => {
        if (msg.type === 'open' && msg.href) void vscode.env.openExternal(vscode.Uri.parse(msg.href));
      });
    }
    this.panel.title = `Gandalf — ${title}`;
    await this.load(htmlPath);
    this.panel.reveal(this.panel.viewColumn, false);
  }

  private async load(htmlPath: string): Promise<void> {
    if (!this.panel || !htmlPath) return;
    this.stale = false;
    const html = await fs.promises.readFile(htmlPath, 'utf8');
    this.panel.webview.html = adapt(html, this.panel.webview);
  }

  dispose(): void {
    this.panel?.dispose();
  }
}
