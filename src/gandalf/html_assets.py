"""The HTML report's stylesheet and script, inline.

Literals rather than files on purpose: the report has to open from a CI
artifact, an email attachment or a file:// URL with nothing to fetch.
"""

CSS = """
:root{ --bg:#fff; --fg:#1b1d22; --muted:#6b7280; --border:#e4e6eb; --card:#f7f8fa;
  --tint:0.15; --pass:#22c55e; --warn:#eab308; --fail:#ef4444; --warn-text:#a16207; }
@media (prefers-color-scheme:dark){ :root:not([data-theme=light]){
  --bg:#0f1115; --fg:#e6e8eb; --muted:#9aa0a6; --border:#272b33; --card:#171a20;
  --tint:0.24; --warn-text:#fbbf24; } }
:root[data-theme=dark]{ --bg:#0f1115; --fg:#e6e8eb; --muted:#9aa0a6; --border:#272b33;
  --card:#171a20; --tint:0.24; --warn-text:#fbbf24; }
*{box-sizing:border-box}
body{ margin:0; background:var(--bg); color:var(--fg); line-height:1.6;
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
.wrap{ width:75%; margin:2.5rem auto; }
@media (max-width:820px){ .wrap{ width:92%; } }
header{ display:flex; align-items:center; justify-content:space-between; gap:1rem; }
h1{ font-size:1.5rem; margin:0; font-weight:700; }
h1 small{ color:var(--muted); font-weight:400; }
.metabar{ margin-top:.6rem; color:var(--muted); font-size:.85rem; }
.metabar code{ background:rgba(127,127,127,.18); padding:.1em .4em; border-radius:5px; }
#themeBtn{ cursor:pointer; border:1px solid var(--border); background:var(--card);
  color:var(--fg); border-radius:9px; padding:.5rem .75rem; font-size:1rem; line-height:1; }
.verdict{ margin:1.25rem 0; padding:1.05rem 1.5rem; border-radius:12px; color:#fff;
  font-size:1.4rem; font-weight:700; letter-spacing:.3px; }
.verdict.pass{ background:var(--pass); } .verdict.warn{ background:var(--warn); }
.verdict.fail{ background:var(--fail); }
.cat-grid{ display:flex; flex-wrap:wrap; gap:.6rem; margin:.2rem 0 .3rem; }
.cat{ flex:1 1 190px; padding:.6rem .85rem; border-radius:10px; color:#fff; }
.cat.pass{ background:var(--pass); } .cat.fail{ background:var(--fail); }
.cat.warn{ background:var(--warn); color:#3a2d00; }
.cat-name{ font-size:.72rem; text-transform:uppercase; letter-spacing:.04em; font-weight:600; opacity:.9; }
.cat-score{ font-size:1.5rem; font-weight:700; line-height:1.1; }
.eyebrow{ text-transform:uppercase; letter-spacing:.08em; font-size:.72rem;
  color:var(--muted); font-weight:600; margin:1.4rem 0 .45rem; }
.summary{ background:var(--card); border:1px solid var(--border); border-radius:12px;
  padding:1.1rem 1.4rem; }
.summary>:first-child{ margin-top:0; } .summary>:last-child{ margin-bottom:0; }
.summary.accent-changeset{ border-left:4px solid #06b6d4; }
.summary.accent-remediation{ border-left:4px solid var(--warn); }
.summary.accent-improvement{ border-left:4px solid #3b82f6; }
.summary h1,.summary h2,.summary h3{ font-size:1.05rem; margin:1rem 0 .4rem; }
.summary code{ background:rgba(127,127,127,.18); padding:.1em .35em; border-radius:5px; font-size:.9em; }
.summary a{ color:#3b82f6; }
.empty-note{ color:var(--muted); font-style:italic; margin:0; }
/* Scroll the table sideways on narrow screens instead of the whole page. */
.table-scroll{ margin-top:1.5rem; overflow-x:auto; -webkit-overflow-scrolling:touch; }
table{ width:100%; min-width:552px; table-layout:fixed; border-collapse:separate;
  border-spacing:0; border:1px solid var(--border); border-radius:12px; overflow:hidden; }
/* Fixed columns so expanding a Detail cell never shifts the others. */
th:nth-child(1),td:nth-child(1){ width:44px; }
th:nth-child(2),td:nth-child(2){ width:270px; }
th:nth-child(3),td:nth-child(3){ width:150px; }
th:nth-child(4),td:nth-child(4){ width:88px; }
th,td{ padding:13px 18px; text-align:left; border-bottom:1px solid var(--border);
  vertical-align:top; word-break:break-word; }
thead th{ background:var(--card); font-size:.78rem; text-transform:uppercase;
  letter-spacing:.05em; color:var(--muted); }
th.sortable{ cursor:pointer; user-select:none; }
th.sortable:hover{ color:var(--fg); }
td.cat-cell{ color:var(--muted); font-size:.85rem; }
tbody tr:last-child td{ border-bottom:none; }
tr.pass td{ background:rgba(34,197,94,var(--tint)); }
tr.warn td{ background:rgba(234,179,8,var(--tint)); }
tr.fail td{ background:rgba(239,68,68,var(--tint)); }
.emoji{ font-size:1.3rem; white-space:nowrap; }
.rag{ font-weight:700; white-space:nowrap; }
.rag.pass{ color:var(--pass); } .rag.warn{ color:var(--warn-text); } .rag.fail{ color:var(--fail); }
.pill{ margin-left:.5rem; font-size:.62rem; text-transform:uppercase; letter-spacing:.05em;
  background:rgba(127,127,127,.2); color:var(--muted); padding:.18em .55em; border-radius:999px;
  vertical-align:middle; font-weight:700; white-space:nowrap; }
.cell-detail small{ display:block; margin-top:.3rem; color:var(--muted); font-size:.8rem;
  word-break:break-word; }
.cell-detail details{ margin-top:.4rem; }
.cell-detail summary{ cursor:pointer; color:var(--muted); font-size:.8rem; user-select:none; }
.cell-detail summary:hover{ color:var(--fg); }
ul.findings{ margin:.45rem 0 0; padding-left:1.1rem; }
ul.findings li{ font-size:.8rem; color:var(--muted); word-break:break-word; margin:.2rem 0;
  font-family:ui-monospace,Menlo,Consolas,monospace; }
/* Remediation: one block; each gate labelled "name (RAG-badge)", failures first. */
.rem-pre{ color:var(--muted); margin:0 0 .7rem; }
.rem-gate{ font-weight:700; margin:1.1rem 0 .35rem; display:flex; align-items:center; gap:.5rem; }
.rem-gate:first-child{ margin-top:0; }
.rem-body{ margin-left:.1rem; }
.rem-body>:first-child{ margin-top:0; } .rem-body>:last-child{ margin-bottom:0; }
.badge{ display:inline-block; font-size:.66rem; font-weight:700; text-transform:uppercase;
  letter-spacing:.04em; padding:.2em .55em; border-radius:6px; color:#fff; }
.badge.fail{ background:var(--fail); } .badge.pass{ background:var(--pass); }
.badge.warn{ background:var(--warn); color:#3a2d00; }
.diff-view{ margin-top:.6rem; }
.diff-view summary{ cursor:pointer; color:var(--muted); font-size:.82rem; user-select:none; }
.diff-view summary:hover{ color:var(--fg); }
.diff-pre{ margin:.5rem 0 0; padding:.9rem 1rem; overflow-x:auto; border-radius:10px;
  background:var(--card); border:1px solid var(--border); font-size:.78rem; line-height:1.5;
  font-family:ui-monospace,Menlo,Consolas,monospace; }
.diff-add{ color:var(--pass); } .diff-del{ color:var(--fail); } .diff-hunk{ color:#3b82f6; }
.filters{ display:flex; gap:.4rem; margin:1.5rem 0 0; }
.filter-btn{ cursor:pointer; border:1px solid var(--border); background:var(--card);
  color:var(--muted); border-radius:999px; padding:.35rem .9rem; font-size:.78rem;
  font-weight:600; }
.filter-btn:hover{ color:var(--fg); }
.filter-btn.active{ background:var(--fg); color:var(--bg); border-color:var(--fg); }
footer{ margin-top:1.8rem; padding-top:.9rem; border-top:1px solid var(--border);
  color:var(--muted); font-size:.8rem; }
footer a{ color:inherit; }
"""

JS = """
(function(){
  var root=document.documentElement, btn=document.getElementById('themeBtn');
  var saved=localStorage.getItem('gandalf-theme'); if(saved) root.dataset.theme=saved;
  function cur(){ return root.dataset.theme ||
    (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'); }
  function paint(){ btn.textContent = cur()==='dark' ? '\\u2600\\uFE0F' : '\\uD83C\\uDF19'; }
  btn.onclick=function(){ var n=cur()==='dark'?'light':'dark';
    root.dataset.theme=n; localStorage.setItem('gandalf-theme',n); paint(); };
  paint();

  // Click-to-sort the Gate / Category / Status columns.
  var tbody=document.querySelector('tbody'), dir={};
  document.querySelectorAll('th.sortable').forEach(function(th){
    th.onclick=function(){
      var key=th.dataset.key;
      var d=dir[key]=dir[key]?-dir[key]:(key==='rag'?-1:1);
      function cmp(a,b){
        if(key==='rag') return d*(+a.dataset.rag - +b.dataset.rag);
        var av=key==='cat'?a.dataset.cat:a.dataset.gate;
        var bv=key==='cat'?b.dataset.cat:b.dataset.gate;
        return d*av.localeCompare(bv) || a.dataset.gate.localeCompare(b.dataset.gate);
      }
      var rows=[].slice.call(tbody.rows);
      rows.sort(cmp);
      rows.forEach(function(r){ tbody.appendChild(r); });
      document.querySelectorAll('th.sortable').forEach(function(x){ x.textContent=x.dataset.label; });
      th.textContent=th.dataset.label+(d===1?' \\u25B2':' \\u25BC');
    };
  });

  // Filter rows by RAG state (pass/warn/fail/all).
  document.querySelectorAll('.filter-btn').forEach(function(b){
    b.onclick=function(){
      document.querySelectorAll('.filter-btn').forEach(function(x){ x.classList.remove('active'); });
      b.classList.add('active');
      var f=b.dataset.filter;
      tbody.querySelectorAll('tr').forEach(function(r){
        r.style.display = (f==='all'||r.classList.contains(f)) ? '' : 'none';
      });
    };
  });
})();
"""
