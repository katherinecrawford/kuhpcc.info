#!/usr/bin/env python3
"""
build_dashboard.py
Reads usage.txt and clean_usage.txt, writes a self-contained index.html.
Run locally or via GitHub Actions.

Usage:
    python build_dashboard.py [--data-dir .] [--out docs/index.html]
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ── parsers ───────────────────────────────────────────────────────────────────

def to_gb(s: str) -> float:
    m = re.match(r"^([0-9.]+)\s*([KMGTP]?B)$", str(s).strip(), re.I)
    if not m:
        return 0.0
    val, unit = float(m.group(1)), m.group(2).upper()
    return {"B": val/1024**3, "KB": val/1024**2, "MB": val/1024,
            "GB": val, "TB": val*1024, "PB": val*1024**2}.get(unit, 0.0)


def parse_usage(path: Path) -> list[dict]:
    if not path.exists():
        print(f"WARNING: {path} not found", file=sys.stderr)
        return []
    lines = path.read_text().splitlines()
    hdr = next((i for i, l in enumerate(lines) if l.startswith("Username,")), None)
    if hdr is None:
        return []
    rows = []
    for line in lines[hdr+1:]:
        parts = line.split(",")
        if len(parts) < 3:
            continue
        username, disk_raw, files_raw = parts[0], parts[1], parts[2]
        if username == "*":
            continue
        gb = to_gb(disk_raw)
        if gb <= 0:
            continue
        rows.append({"username": username, "disk_gb": round(gb, 3),
                     "files_used": int(files_raw.strip()) if files_raw.strip().isdigit() else 0})
    rows.sort(key=lambda r: r["disk_gb"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


def parse_summary(path: Path) -> dict:
    out = {"updated": "unknown", "total": "—", "used": "—",
           "avail": "—", "pct": "—", "pct_num": 0, "allotment": "—"}
    if not path.exists():
        print(f"WARNING: {path} not found", file=sys.stderr)
        return out
    for line in path.read_text().splitlines():
        if line.startswith("Updated:"):
            out["updated"] = line.replace("Updated:", "").strip()
        m = re.match(r"^(\d+\S*)\s+(\d+\S*)\s+(\S+)\s+(\d+)%", line)
        if m:
            out["total"], out["used"], out["avail"] = m.group(1), m.group(2), m.group(3)
            out["pct"] = f"{m.group(4)}%"
            out["pct_num"] = int(m.group(4))
        if "allotment =" in line:
            vals = re.findall(r"\d+GB", line)
            if vals:
                out["allotment"] = vals[0]
    return out


# ── HTML template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>BI Work Storage Monitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Syne:wght@400;700;800&display=swap" rel="stylesheet"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#080b10;--surface:#0e1318;--surface2:#141a21;
  --border:#1e262f;--border2:#2a3540;
  --accent:#ff6b4a;--blue:#5eb8ff;--green:#3dd68c;--yellow:#f5c842;
  --text:#cdd9e5;--muted:#5a6a78;--mono:'IBM Plex Mono',monospace;
  --display:'Syne',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--mono);min-height:100vh;
  background-image:radial-gradient(ellipse 80% 50% at 50% -10%,#0d2030 0%,transparent 70%)}

/* ── header ── */
header{
  padding:28px 36px 24px;
  border-bottom:1px solid var(--border);
  display:flex;align-items:flex-end;justify-content:space-between;flex-wrap:wrap;gap:12px;
}
.logo{font-family:var(--display);font-size:1.5rem;font-weight:800;color:var(--blue);
  letter-spacing:-.02em;line-height:1}
.logo span{color:var(--accent)}
.meta{font-size:.7rem;color:var(--muted);line-height:1.8;text-align:right}
.meta b{color:var(--text)}

/* ── tiles ── */
.tiles{display:flex;gap:10px;padding:24px 36px 0;flex-wrap:wrap}
.tile{
  background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:16px 20px;flex:1;min-width:110px;position:relative;overflow:hidden;
  transition:border-color .2s;
}
.tile:hover{border-color:var(--border2)}
.tile::before{content:'';position:absolute;inset:0;
  background:linear-gradient(135deg,rgba(255,255,255,.02) 0%,transparent 60%)}
.tile-label{font-size:.6rem;color:var(--muted);text-transform:uppercase;
  letter-spacing:.1em;margin-bottom:8px}
.tile-value{font-size:1.6rem;font-weight:600;font-family:var(--display);line-height:1}
.c-blue{color:var(--blue)}.c-yellow{color:var(--yellow)}
.c-green{color:var(--green)}.c-accent{color:var(--accent)}

/* ── usage bar ── */
.bar-section{margin:20px 36px 0;
  background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px 20px}
.bar-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.bar-title{font-size:.65rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.bar-pct{font-family:var(--display);font-size:1.1rem;font-weight:700;color:var(--text)}
.bar-track{background:var(--border2);border-radius:4px;height:12px;overflow:hidden}
.bar-fill{height:12px;border-radius:4px;transition:width 1s cubic-bezier(.4,0,.2,1)}

/* ── controls ── */
.controls{display:flex;gap:12px;padding:20px 36px 0;flex-wrap:wrap;align-items:flex-end}
.ctrl-group label{display:block;font-size:.6rem;color:var(--muted);text-transform:uppercase;
  letter-spacing:.1em;margin-bottom:5px}
.ctrl-group input,.ctrl-group select{
  background:var(--surface2);border:1px solid var(--border2);color:var(--text);
  font-family:var(--mono);font-size:.82rem;padding:7px 11px;border-radius:6px;outline:none;
  transition:border-color .15s;
}
.ctrl-group input:focus,.ctrl-group select:focus{border-color:var(--blue)}
select option{background:var(--surface2)}

/* ── main chart panel ── */
.chart-wrap{padding:16px 36px 0}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:18px}
.panel-title{font-size:.65rem;text-transform:uppercase;letter-spacing:.1em;
  color:var(--blue);margin-bottom:14px}

/* ── table ── */
.table-wrap{margin:14px 36px 36px;
  background:var(--surface);border:1px solid var(--border);border-radius:8px;
  overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.78rem}
thead th{padding:10px 14px;font-size:.62rem;text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);font-weight:400;border-bottom:1px solid var(--border);
  text-align:left;white-space:nowrap;position:sticky;top:0;background:var(--surface);
  cursor:pointer;user-select:none}
thead th:hover{color:var(--text)}
thead th.sorted{color:var(--blue)}
thead th .sort-arrow{margin-left:4px;opacity:.5;font-style:normal}
thead th.sorted .sort-arrow{opacity:1}
tbody tr{transition:background .1s}
tbody tr:hover td{background:#111820}
tbody td{padding:6px 14px;border-bottom:1px solid #0f151b;white-space:nowrap}
.td-rank{color:var(--muted)}
.td-user{color:var(--blue);font-weight:600}
.td-disk{color:var(--yellow);font-weight:600}
.td-files{color:var(--muted)}
.minibar-wrap{width:100px;background:var(--border2);border-radius:3px;height:7px;overflow:hidden}
.minibar-fill{height:7px;border-radius:3px}

/* ── animations ── */
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.tile{animation:fadeUp .4s ease both}
.tile:nth-child(1){animation-delay:.05s}.tile:nth-child(2){animation-delay:.1s}
.tile:nth-child(3){animation-delay:.15s}.tile:nth-child(4){animation-delay:.2s}
.tile:nth-child(5){animation-delay:.25s}.tile:nth-child(6){animation-delay:.3s}
.panel{animation:fadeUp .5s ease .2s both}

/* ── footer ── */
footer{padding:16px 36px;font-size:.65rem;color:var(--muted);border-top:1px solid var(--border);
  margin-top:8px;display:flex;gap:8px;flex-wrap:wrap}
footer a{color:var(--muted);text-decoration:none}
footer a:hover{color:var(--blue)}
</style>
</head>
<body>

<header>
  <div class="logo">BI<span>.</span>storage</div>
  <div class="meta">
    <div>Updated: <b id="ts-updated">__UPDATED__</b></div>
    <div>Built: <b id="ts-built">__BUILT__</b></div>
  </div>
</header>

<div class="tiles">
  <div class="tile"><div class="tile-label">Total</div>
    <div class="tile-value c-blue">__TOTAL__</div></div>
  <div class="tile"><div class="tile-label">Used</div>
    <div class="tile-value c-yellow">__USED__</div></div>
  <div class="tile"><div class="tile-label">Available</div>
    <div class="tile-value c-green">__AVAIL__</div></div>
  <div class="tile"><div class="tile-label">Utilisation</div>
    <div class="tile-value c-accent">__PCT__</div></div>
  <div class="tile"><div class="tile-label">Active Users</div>
    <div class="tile-value c-blue">__USERS__</div></div>
  <div class="tile"><div class="tile-label">Allotment</div>
    <div class="tile-value c-green">__ALLOT__</div></div>
</div>

<div class="bar-section">
  <div class="bar-header">
    <span class="bar-title">Storage utilisation</span>
    <span class="bar-pct">__PCT__</span>
  </div>
  <div class="bar-track">
    <div class="bar-fill" id="main-bar"
         style="width:__PCT_NUM__%;"
    ></div>
  </div>
</div>

<div class="controls">
  <div class="ctrl-group">
    <label>Top N users</label>
    <input type="number" id="ctrl-topn" value="25" min="5" max="500" style="width:80px"/>
  </div>
  <div class="ctrl-group">
    <label>Min disk (GB)</label>
    <input type="number" id="ctrl-mingb" value="0" min="0" style="width:95px"/>
  </div>
  <div class="ctrl-group">
    <label>Chart metric</label>
    <select id="ctrl-metric">
      <option value="disk_gb">Disk Used</option>
      <option value="files_used">Files Used</option>
    </select>
  </div>
</div>

<div class="chart-wrap">
  <div class="panel">
    <div class="panel-title">Top Users</div>
    <canvas id="bar-chart" height="340"></canvas>
  </div>
</div>

<div class="table-wrap">
  <table id="user-table">
    <thead>
      <tr>
        <th data-col="rank" class="sorted"># <i class="sort-arrow">↓</i></th>
        <th data-col="username">Username <i class="sort-arrow">↕</i></th>
        <th data-col="disk_gb">Disk Used <i class="sort-arrow">↕</i></th>
        <th data-col="files_used">Files <i class="sort-arrow">↕</i></th>
        <th>Usage</th>
      </tr>
    </thead>
    <tbody id="table-body"></tbody>
  </table>
</div>

<footer>
  <span>BI Work Storage Monitor</span>
  <span>·</span>
  <span>Data refreshes hourly via cron → GitHub Actions → GitHub Pages</span>
</footer>

<script>
// ── embedded data ─────────────────────────────────────────────────────────────
const ALL_ROWS = __JSON_DATA__;

// ── chart.js defaults ─────────────────────────────────────────────────────────
Chart.defaults.color = '#5a6a78';
Chart.defaults.font.family = "'IBM Plex Mono', monospace";
Chart.defaults.font.size = 10;

const C = {
  accent:'#ff6b4a', blue:'#5eb8ff', green:'#3dd68c', yellow:'#f5c842',
  muted:'#5a6a78', border:'#1e262f', surface:'#0e1318', bg:'#080b10'
};

// ── bar chart ─────────────────────────────────────────────────────────────────
let barChart;

function gradientColors(ctx, count) {
  const g = ctx.createLinearGradient(0,0,400,0);
  g.addColorStop(0, C.yellow);
  g.addColorStop(1, C.accent);
  return g;
}

function buildBarChart(rows, metric) {
  const sorted = [...rows].sort((a,b) => b[metric] - a[metric]).slice(0, 30);
  const labels = sorted.map(r => r.username);
  const vals   = sorted.map(r => r[metric]);
  const label  = metric === 'disk_gb' ? 'Disk (GB)' : 'Files';

  if (barChart) barChart.destroy();
  const ctx = document.getElementById('bar-chart').getContext('2d');
  barChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label,
        data: vals,
        backgroundColor: gradientColors(ctx, vals.length),
        borderWidth: 0,
        borderRadius: 3,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 500, easing: 'easeOutQuart' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: C.bg,
          borderColor: C.border,
          borderWidth: 1,
          titleColor: C.blue,
          bodyColor: C.muted,
          callbacks: {
            label: ctx => metric === 'disk_gb'
              ? ` ${ctx.parsed.x.toLocaleString(undefined,{maximumFractionDigits:1})} GB`
              : ` ${ctx.parsed.x.toLocaleString()} files`
          }
        }
      },
      scales: {
        x: { grid:{color:C.border}, ticks:{color:C.muted} },
        y: { grid:{display:false}, ticks:{color:C.blue, font:{size:10}} }
      }
    }
  });
}

// ── table ─────────────────────────────────────────────────────────────────────
let sortCol = 'rank', sortAsc = true;

function buildTable(rows) {
  const maxGb = Math.max(...rows.map(r => r.disk_gb), 1);
  const tbody = document.getElementById('table-body');
  tbody.innerHTML = '';
  rows.forEach(r => {
    const pct = (r.disk_gb / maxGb * 100).toFixed(1);
    const fillCol = r.disk_gb > maxGb * .8 ? C.accent
                  : r.disk_gb > maxGb * .4 ? C.yellow : C.green;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="td-rank">${r.rank}</td>
      <td class="td-user">${r.username}</td>
      <td class="td-disk">${r.disk_gb.toFixed(2)} GB</td>
      <td class="td-files">${r.files_used.toLocaleString()}</td>
      <td><div class="minibar-wrap">
        <div class="minibar-fill" style="width:${pct}%;background:${fillCol}"></div>
      </div></td>`;
    tbody.appendChild(tr);
  });
}

// ── sorting ───────────────────────────────────────────────────────────────────
document.querySelectorAll('thead th[data-col]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.col;
    if (sortCol === col) sortAsc = !sortAsc;
    else { sortCol = col; sortAsc = col === 'username'; }
    document.querySelectorAll('thead th').forEach(t => {
      t.classList.remove('sorted');
      const arr = t.querySelector('.sort-arrow');
      if (arr) arr.textContent = '↕';
    });
    th.classList.add('sorted');
    const arr = th.querySelector('.sort-arrow');
    if (arr) arr.textContent = sortAsc ? '↑' : '↓';
    render();
  });
});

// ── main render ───────────────────────────────────────────────────────────────
function render() {
  const topN  = parseInt(document.getElementById('ctrl-topn').value)  || 25;
  const minGb = parseFloat(document.getElementById('ctrl-mingb').value) || 0;
  const metric = document.getElementById('ctrl-metric').value;

  let rows = ALL_ROWS.filter(r => r.disk_gb >= minGb);

  // sort for table
  rows.sort((a, b) => {
    const av = a[sortCol], bv = b[sortCol];
    if (typeof av === 'string') return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    return sortAsc ? av - bv : bv - av;
  });
  const tableRows = rows.slice(0, topN);
  buildTable(tableRows);

  // charts use top-N by disk regardless of table sort
  const chartRows = [...rows].sort((a,b) => b.disk_gb - a.disk_gb).slice(0, topN);
  buildBarChart(chartRows, metric);
}

// ── usage bar colour ──────────────────────────────────────────────────────────
(function(){
  const pct = __PCT_NUM__;
  const bar = document.getElementById('main-bar');
  const col = pct >= 95 ? '#ff6b4a' : pct >= 85 ? '#f5c842' : '#3dd68c';
  bar.style.background = col;
})();

// ── controls ──────────────────────────────────────────────────────────────────
['ctrl-topn','ctrl-mingb','ctrl-metric'].forEach(id =>
  document.getElementById(id).addEventListener('input', render));

// ── init ─────────────────────────────────────────────────────────────────────
render();
</script>
</body>
</html>
"""


# ── builder ───────────────────────────────────────────────────────────────────

def build(data_dir: Path, out_path: Path):
    from datetime import datetime, timezone
    rows   = parse_usage(data_dir / "usage.txt")
    summ   = parse_summary(data_dir / "clean_usage.txt")
    built  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = HTML_TEMPLATE
    html = html.replace("__UPDATED__",  summ["updated"])
    html = html.replace("__BUILT__",    built)
    html = html.replace("__TOTAL__",    summ["total"])
    html = html.replace("__USED__",     summ["used"])
    html = html.replace("__AVAIL__",    summ["avail"])
    html = html.replace("__PCT__",      summ["pct"])
    html = html.replace("__PCT_NUM__",  str(summ["pct_num"]))
    html = html.replace("__USERS__",    str(len(rows)))
    html = html.replace("__ALLOT__",    summ["allotment"])
    html = html.replace("__JSON_DATA__", json.dumps(rows, separators=(",", ":")))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"✓  Wrote {out_path}  ({len(rows)} users, {out_path.stat().st_size//1024} KB)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, default=Path("."))
    p.add_argument("--out",      type=Path, default=Path("docs/index.html"))
    args = p.parse_args()
    build(args.data_dir.resolve(), args.out.resolve())
