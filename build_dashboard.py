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
           "avail": "—", "pct": "—", "pct_num": 0, "allotment": "—",
           "allotments": []}  # list of {label, gb} for reference lines
    if not path.exists():
        print(f"WARNING: {path} not found", file=sys.stderr)
        return out
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("Updated:"):
            out["updated"] = line.replace("Updated:", "").strip()
        m = re.match(r"^(\d+\S*)\s+(\d+\S*)\s+(\S+)\s+(\d+)%", line)
        if m:
            out["total"], out["used"], out["avail"] = m.group(1), m.group(2), m.group(3)
            out["pct"] = f"{m.group(4)}%"
            out["pct_num"] = int(m.group(4))
        # header row: "per current # users >=  1GB  10GB  100GB  1000GB"
        if "per current # users" in line:
            thresholds = re.findall(r"\d+GB", line)
            # next non-empty line has the allotment values
            for next_line in lines[i+1:]:
                if "allotment =" in next_line:
                    vals = re.findall(r"[\d.]+GB", next_line)
                    if vals:
                        out["allotment"] = vals[0]  # >=1GB tier for the tile
                    # pair each threshold label with its allotment value
                    out["allotments"] = [
                        {"label": f"≥{t} share", "gb": to_gb(v)}
                        for t, v in zip(thresholds, vals)
                    ]
                    break
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
/* ── main chart panel ── */
.chart-wrap{padding:16px 36px 0}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:18px}
.chart-container{position:relative;height:420px}
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
/* ── stale data warning ── */
.stale-warn{display:none;background:#3a0d0d;border:1px solid var(--accent);
  color:var(--accent);font-size:.65rem;padding:4px 10px;border-radius:4px;
  font-family:var(--mono);white-space:nowrap;align-self:center}
.stale-warn.visible{display:inline-block}
</style>
</head>
<body>

<header>
  <div class="logo">BI<span>.</span>storage</div>
  <div class="meta" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;justify-content:flex-end">
    <span class="stale-warn" id="stale-warn">⚠ Warning: data may be outdated</span>
    <div style="text-align:right">
      <div>Updated: <b>__UPDATED__</b></div>
      <div>Built: <b>__BUILT__</b></div>
    </div>
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
  <div class="tile"><div class="tile-label">Users</div>
    <div class="tile-value c-green">__USERS__</div></div>
  <div class="tile"><div class="tile-label">Equal Allotment</div>
    <div class="tile-value c-blue">__ALLOT__</div></div>
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

<div class="chart-wrap">
  <div class="panel">
    <div class="panel-title">Top Users</div>
    <div class="chart-container"><canvas id="bar-chart"></canvas></div>
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
const ALLOTMENTS = __ALLOTMENTS__;  // [{label, gb}, ...] for >=1/10/100/1000GB tiers

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

function buildBarChart(rows) {
  const TOP_N = 25;
  const sorted = [...rows].sort((a, b) => b.disk_gb - a.disk_gb).slice(0, TOP_N);
  const labels = sorted.map(r => r.username);
  const vals   = sorted.map(r => r.disk_gb);

  const refColors = ['#5eb8ff','#3dd68c','#f5c842','#ff6b4a'];
  const refDatasets = ALLOTMENTS.map((a, i) => ({
    label: `${a.label} (${a.gb.toLocaleString(undefined,{maximumFractionDigits:0})} GB)`,
    data: labels.map(() => a.gb),
    type: 'line',
    borderColor: refColors[i % refColors.length],
    borderWidth: 1.5,
    borderDash: [4, 3],
    pointRadius: 0,
    fill: false,
    tension: 0,
    order: 0,
  }));

  if (barChart) barChart.destroy();
  const ctx = document.getElementById('bar-chart').getContext('2d');
  const grad = ctx.createLinearGradient(0, 0, 400, 0);
  grad.addColorStop(0, C.yellow);
  grad.addColorStop(1, C.accent);

  barChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Disk (GB)',
          data: vals,
          backgroundColor: grad,
          borderWidth: 0,
          borderRadius: 2,
          categoryPercentage: 0.6,  // 60% of slot used by bar group → 40% gap
          barPercentage: 1.0,        // bar fills its group fully
          order: 1,
        },
        ...refDatasets,
      ]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 500, easing: 'easeOutQuart' },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          align: 'end',
          labels: {
            color: C.muted,
            font: { size: 10 },
            boxWidth: 20,
            boxHeight: 1,
            filter: item => item.text !== 'Disk (GB)',
          }
        },
        tooltip: {
          backgroundColor: C.bg,
          borderColor: C.border,
          borderWidth: 1,
          titleColor: C.blue,
          bodyColor: C.muted,
          callbacks: {
            label: ctx => {
              if (ctx.dataset.type === 'line')
                return ` ${ctx.dataset.label}`;
              return ` ${ctx.parsed.x.toLocaleString(undefined,{maximumFractionDigits:1})} GB`;
            }
          }
        }
      },
      scales: {
        x: { grid:{color:C.border}, ticks:{color:C.muted} },
        y: { grid:{display:false}, ticks:{color:C.blue, font:{size:10}, autoSkip:false} }
      }
    }
  });
}

// ── table ─────────────────────────────────────────────────────────────────────
let sortCol = 'rank', sortAsc = true;

// colour based on actual allotment thresholds, highest tier first
function tierColor(gb) {
  const colors = ['#5eb8ff','#3dd68c','#f5c842','#ff6b4a'];
  for (let i = ALLOTMENTS.length - 1; i >= 0; i--) {
    if (gb >= ALLOTMENTS[i].gb) return colors[i];
  }
  return C.muted;
}

function buildTable(rows) {
  const maxGb = Math.max(...ALL_ROWS.map(x => x.disk_gb), 1);  // hoisted — constant for all rows
  const tbody = document.getElementById('table-body');
  tbody.innerHTML = '';
  rows.forEach(r => {
    const pct = (r.disk_gb / maxGb * 100).toFixed(1);
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="td-rank">${r.rank}</td>
      <td class="td-user">${r.username}</td>
      <td class="td-disk">${r.disk_gb.toFixed(2)} GB</td>
      <td class="td-files">${r.files_used.toLocaleString()}</td>
      <td><div class="minibar-wrap">
        <div class="minibar-fill" style="width:${pct}%;background:${tierColor(r.disk_gb)}"></div>
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
    const arrow = th.querySelector('.sort-arrow');
    if (arrow) arrow.textContent = sortAsc ? '↑' : '↓';
    render();
  });
});

// ── stale data warning ────────────────────────────────────────────────────────
(function() {
  const updated = '__UPDATED__';
  // parse the timestamp — format: "Thu May 14 19:30:45 CDT 2026"
  const parsed = Date.parse(updated);
  if (!isNaN(parsed) && (Date.now() - parsed) > 12 * 60 * 60 * 1000) {
    document.getElementById('stale-warn').classList.add('visible');
  }
})();

// ── usage bar colour ──────────────────────────────────────────────────────────
(function() {
  const pct = __PCT_NUM__;
  const col = pct >= 95 ? '#ff6b4a' : pct >= 85 ? '#f5c842' : '#3dd68c';
  document.getElementById('main-bar').style.background = col;
})();

// ── main render ───────────────────────────────────────────────────────────────
function render() {
  buildTable([...ALL_ROWS].sort((a, b) => {
    const av = a[sortCol], bv = b[sortCol];
    if (typeof av === 'string') return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    return sortAsc ? av - bv : bv - av;
  }));
  buildBarChart(ALL_ROWS);
}

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
    html = html.replace("__JSON_DATA__",  json.dumps(rows, separators=(",", ":")))
    html = html.replace("__ALLOTMENTS__", json.dumps(summ["allotments"], separators=(",", ":")))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"✓  Wrote {out_path}  ({len(rows)} users, {out_path.stat().st_size//1024} KB)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, default=Path("."))
    p.add_argument("--out",      type=Path, default=Path("docs/index.html"))
    args = p.parse_args()
    build(args.data_dir.resolve(), args.out.resolve())
