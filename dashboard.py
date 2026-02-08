#!/usr/bin/env python3
"""
ASE Traffic Control Plane — Streamlit Monitoring Dashboard
Real-time statistics and detailed logs for the C++ UDP Packet Processor.
Run server and monitor manually in the terminal; use this for metrics + log view.
Industry-style observability: throughput rates, per-worker throughput, load balance, time-series.
"""

import html
import math
import re
import struct
import mmap
import time
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# --- Paths (project root = directory of this script) ---
PROJECT_DIR = Path(__file__).resolve().parent
SERVER_LOG = PROJECT_DIR / "server.log"
CLIENT_LOG = PROJECT_DIR / "client.log"
SHM_PATH = "/dev/shm/telecom_shm"

# SystemStats layout (must match protocol.h): 3*uint64, uint64 start_time, bool, 7 pad, 4*uint64
STATS_STRUCT_FMT = "<QQQQB7x4Q"
STATS_STRUCT_SIZE = struct.calcsize(STATS_STRUCT_FMT)


def read_shm_stats():
    """Read SystemStats from shared memory. Returns None if shm missing or error."""
    try:
        with open(SHM_PATH, "rb") as f:
            with mmap.mmap(f.fileno(), length=STATS_STRUCT_SIZE, access=mmap.ACCESS_READ) as m:
                raw = m.read(STATS_STRUCT_SIZE)
    except FileNotFoundError:
        return None
    except Exception:
        return None
    if len(raw) < STATS_STRUCT_SIZE:
        return None
    t = struct.unpack(STATS_STRUCT_FMT, raw)
    return {
        "packets_processed": t[0],
        "bytes_transferred": t[1],
        "dropped_packets": t[2],
        "start_time_sec": t[3],
        "is_running": bool(t[4]),
        "thread_load": list(t[5:9]),  # 4 x uint64 after bool + 7-byte pad
    }


# ISO8601 timestamp at start of line: [2025-02-07T12:34:56.123Z]
_LOG_TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)\]\s*")


def _parse_log_timestamp(s):
    """Parse ISO8601 UTC string to epoch seconds. Returns None on failure."""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None


def read_log_with_timestamps(path, max_bytes=2 * 1024 * 1024):
    """
    Read log file (tail up to max_bytes). Return list of (epoch_sec or None, line_text).
    Lines with leading [YYYY-MM-DDTHH:MM:SS.mmmZ] are parsed for time filtering.
    """
    path = Path(path)
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size <= max_bytes:
                raw = f.read()
            else:
                f.seek(max(0, size - max_bytes))
                raw = f.read()
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
    except Exception:
        return []
    out = []
    for line in lines:
        line = line.strip("\r\n")
        m = _LOG_TS_RE.match(line)
        if m:
            ts = _parse_log_timestamp(m.group(1))
            rest = line[m.end() :]
            out.append((ts, rest))
        else:
            out.append((None, line))
    return out


# Drop/validation reasons (tag, pattern) — order matters for first match
DROP_VALIDATION_PATTERNS = [
    ("MAGIC_WORD", "Invalid magic word"),
    ("CHECKSUM", "Checksum mismatch"),
    ("TOO_SMALL", "Packet too small"),
    ("TOO_LARGE", "Packet too large"),
    ("SIZE_MISMATCH", "Packet size mismatch"),
    ("LISTENER_ERROR", "recvfrom error"),
]


def tag_drop_line(line):
    """Return (tag, display_line) for a drop/validation line, or (None, line)."""
    for tag, pattern in DROP_VALIDATION_PATTERNS:
        if pattern in line:
            return (tag, line)
    return (None, line)


def parse_drop_reason_and_details(line):
    """
    Parse server drop log line into a human-readable reason and key details for display.
    Returns (reason_summary, details_list).
    details_list is a list of (label, value) for expected/received etc.
    """
    details = []
    reason = "Validation failure"
    if "Invalid magic word" in line:
        m = re.search(r"Invalid magic word:\s*0x([0-9a-fA-F]+)", line)
        received = m.group(1) if m else "?"
        reason = "Invalid magic word — packet sync marker did not match."
        details = [("Received (hex)", f"0x{received}"), ("Expected (hex)", "0xDEADBEEF")]
    elif "Checksum mismatch" in line:
        m = re.search(r"Expected:\s*(\d+)\s*,\s*calculated:\s*(\d+)", line)
        if m:
            details = [("Expected checksum", m.group(1)), ("Calculated checksum", m.group(2))]
        reason = "Checksum mismatch — packet integrity check failed."
    elif "Packet too small" in line:
        m = re.search(r"Packet too small:\s*(\d+)\s*bytes\s*\(min:\s*(\d+)\)", line)
        if m:
            details = [("Received size", f"{m.group(1)} bytes"), ("Minimum (header)", f"{m.group(2)} bytes")]
        reason = "Packet too small — shorter than header size."
    elif "Packet too large" in line:
        m = re.search(r"Packet too large:\s*(\d+)\s*bytes\s*\(max:\s*(\d+)\)", line)
        if m:
            details = [("Received size", f"{m.group(1)} bytes"), ("Maximum allowed", f"{m.group(2)} bytes")]
        reason = "Packet too large — exceeds buffer limit."
    elif "Packet size mismatch" in line:
        m = re.search(r"Expected:\s*(\d+)\s*,\s*received:\s*(\d+)", line)
        if m:
            details = [("Expected (header + payload)", f"{m.group(1)} bytes"), ("Received", f"{m.group(2)} bytes")]
        reason = "Packet size mismatch — payload length in header does not match received bytes."
    elif "recvfrom error" in line:
        m = re.search(r"recvfrom error:\s*(.+)", line)
        err = m.group(1).strip() if m else line
        details = [("Error", err)]
        reason = "Listener recvfrom error — socket read failed."
    return (reason, details)


def tail_log(path, lines=20, max_bytes=256 * 1024):
    """Last N lines of a file. Reads from end only (fast for large logs)."""
    path = Path(path)
    if not path.exists():
        return "(no log file)"
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size <= max_bytes:
                raw = f.read()
            else:
                f.seek(max(0, size - max_bytes))
                raw = f.read()
        text = raw.decode("utf-8", errors="replace")
        line_list = text.splitlines()
        return "\n".join(line_list[-lines:]) if line_list else ""
    except Exception as e:
        return f"(error reading log: {e})"


def uptime_str(start_time_sec, is_running):
    if not is_running or start_time_sec == 0:
        return "—"
    now = int(time.time())
    delta = max(0, now - start_time_sec)
    h, r = divmod(delta, 3600)
    m, s = divmod(r, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _ensure_rate_state():
    """Initialize session state for rate-based metrics and throughput history."""
    if "prev_stats" not in st.session_state:
        st.session_state.prev_stats = None
        st.session_state.prev_ts = None
        st.session_state.throughput_history = []  # list of (timestamp, packets_per_sec)
        st.session_state.max_history = 60  # ~2 min at 2s refresh


def compute_rates(stats):
    """
    Compute packets/s, bytes/s, drop rate, and per-worker packets/s from current stats.
    Returns dict with keys: packets_per_sec, bytes_per_sec, drops_per_sec, drop_pct, worker_pps, load_balance_cv.
    """
    _ensure_rate_state()
    now = time.time()
    prev = st.session_state.prev_stats
    prev_ts = st.session_state.prev_ts
    elapsed = (now - prev_ts) if prev_ts and (now - prev_ts) > 0 else 2.0  # default 2s

    out = {
        "packets_per_sec": 0.0,
        "bytes_per_sec": 0.0,
        "drops_per_sec": 0.0,
        "drop_pct": 0.0,
        "worker_pps": [0.0, 0.0, 0.0, 0.0],
        "load_balance_cv": 0.0,
    }

    if not stats:
        st.session_state.prev_stats = None
        st.session_state.prev_ts = now
        return out

    curr_load = (list(stats["thread_load"]) + [0] * 4)[:4]
    curr_packets = stats["packets_processed"]
    curr_bytes = stats["bytes_transferred"]
    curr_drops = stats["dropped_packets"]

    if prev is not None and prev_ts is not None:
        prev_load = (list(prev.get("thread_load") or []) + [0] * 4)[:4]
        delta_p = curr_packets - prev.get("packets_processed", 0)
        delta_b = curr_bytes - prev.get("bytes_transferred", 0)
        delta_d = curr_drops - prev.get("dropped_packets", 0)
        out["packets_per_sec"] = max(0, delta_p / elapsed)
        out["bytes_per_sec"] = max(0, delta_b / elapsed)
        out["drops_per_sec"] = max(0, delta_d / elapsed)
        out["drop_pct"] = (100 * delta_d / delta_p) if delta_p > 0 else 0.0
        for i in range(4):
            out["worker_pps"][i] = max(0, (curr_load[i] - prev_load[i]) / elapsed)
        # Coefficient of variation (std/mean) for load balance: 0 = perfectly balanced
        rates = out["worker_pps"]
        mean_r = sum(rates) / 4 if rates else 0
        if mean_r > 0:
            variance = sum((r - mean_r) ** 2 for r in rates) / 4
            out["load_balance_cv"] = math.sqrt(variance) / mean_r
        # Append to throughput history
        hist = st.session_state.throughput_history
        hist.append((now, out["packets_per_sec"]))
        if len(hist) > st.session_state.max_history:
            st.session_state.throughput_history = hist[-st.session_state.max_history :]

    st.session_state.prev_stats = {
        "packets_processed": curr_packets,
        "bytes_transferred": curr_bytes,
        "dropped_packets": curr_drops,
        "thread_load": list(curr_load),
    }
    st.session_state.prev_ts = now
    return out


# --- Page config and dark theme ---
st.set_page_config(
    page_title="ASE Traffic Control Plane",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* Apple-style minimalist dark theme (no external font for faster load) */
    html, body, [class*="css"] {
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .stApp {
        background: linear-gradient(180deg, #0d0d0d 0%, #1a1a1a 100%);
    }
    header[data-testid="stHeader"] {
        background: rgba(0,0,0,0.3);
    }
    .main-title {
        font-size: 1.75rem;
        font-weight: 600;
        letter-spacing: -0.02em;
        color: #f5f5f7;
        margin-bottom: 0.5rem;
    }
    .metric-card {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin: 0.25rem 0;
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: 600;
        color: #f5f5f7;
    }
    .metric-label {
        font-size: 0.8rem;
        color: #86868b;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .status-live {
        color: #30d158;
        font-weight: 500;
    }
    .status-down {
        color: #ff453a;
        font-weight: 500;
    }
    .delta-bad {
        color: #ff453a;
        font-weight: 500;
    }
    .log-box {
        background: #0d0d0d;
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 0.8rem;
        color: #a1a1a6;
        max-height: 420px;
        overflow-y: auto;
        white-space: pre-wrap;
        word-break: break-all;
    }
    .worker-card {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.5rem;
    }
    .worker-card .worker-name {
        font-size: 0.85rem;
        color: #86868b;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 0.35rem;
    }
    .worker-card .worker-value {
        font-size: 1.5rem;
        font-weight: 600;
        color: #f5f5f7;
        margin-bottom: 0.15rem;
    }
    .worker-card .worker-util {
        font-size: 0.8rem;
        color: #86868b;
        margin-bottom: 0.5rem;
    }
    .worker-bar-track {
        background: rgba(255,255,255,0.1);
        border-radius: 6px;
        height: 10px;
        overflow: hidden;
    }
    .worker-bar-fill {
        height: 100%;
        border-radius: 6px;
        min-width: 4px;
        transition: width 0.3s ease;
    }
    .worker-bar-fill.w1 { background: linear-gradient(90deg, #30d158, #34c759); }
    .worker-bar-fill.w2 { background: linear-gradient(90deg, #64d2ff, #5ac8fa); }
    .worker-bar-fill.w3 { background: linear-gradient(90deg, #bf5af2, #af52de); }
    .worker-bar-fill.w4 { background: linear-gradient(90deg, #ff9f0a, #ff9500); }
    .chart-row { display: flex; align-items: center; margin-bottom: 0.6rem; gap: 1rem; }
    .chart-row .chart-label { width: 72px; font-size: 0.85rem; color: #a1a1a6; }
    .chart-row .chart-bar-wrap { flex: 1; background: rgba(255,255,255,0.1); border-radius: 6px; height: 28px; overflow: hidden; }
    .chart-row .chart-bar { height: 100%; border-radius: 6px; min-width: 4px; transition: width 0.3s ease; }
    .chart-row .chart-val { font-size: 0.9rem; font-weight: 500; color: #f5f5f7; min-width: 5rem; text-align: right; }
    .section-label { font-size: 0.75rem; color: #86868b; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.5rem; }
    .sparkline-wrap { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 0.5rem 0.75rem; margin-top: 0.5rem; }
    .balance-ok { color: #30d158; }
    .balance-warn { color: #ff9f0a; }
    .balance-bad { color: #ff453a; }
    .log-tag { font-size: 0.7rem; font-weight: 600; padding: 0.15rem 0.4rem; border-radius: 4px; margin-right: 0.5rem; }
    .log-tag-magic_word { background: rgba(255,149,0,0.25); color: #ff9f0a; }
    .log-tag-checksum { background: rgba(255,69,58,0.25); color: #ff453a; }
    .log-tag-too_small, .log-tag-too_large { background: rgba(191,90,242,0.25); color: #bf5af2; }
    .log-tag-size_mismatch { background: rgba(100,210,255,0.25); color: #64d2ff; }
    .log-tag-listener_error { background: rgba(255,69,58,0.3); color: #ff453a; }
    .log-line { margin-bottom: 0.35rem; }
    .log-box-drops { max-height: 480px; }
    .drop-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 0.75rem; }
    .drop-card .drop-reason { font-weight: 600; color: #f5f5f7; margin-bottom: 0.4rem; }
    .drop-card .drop-details { font-size: 0.85rem; color: #a1a1a6; margin-bottom: 0.4rem; }
    .drop-card .drop-details span { margin-right: 1rem; }
    .drop-card .drop-details kbd { background: rgba(255,255,255,0.1); padding: 0.1rem 0.35rem; border-radius: 4px; font-size: 0.8rem; }
    .drop-card .drop-raw { font-size: 0.8rem; font-family: Consolas, Monaco, monospace; color: #86868b; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 0.4rem; margin-top: 0.25rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Sidebar: info and log filters (industry-style: time range + category) ---
with st.sidebar:
    st.markdown("### Info")
    st.markdown("Run **server**, **monitor**, and **client** in separate terminals. This dashboard shows live statistics and server/client log tails.")
    st.markdown("---")
    st.markdown("### Log filters")
    time_range = st.selectbox(
        "Time range",
        ["Last 1h", "Last 6h", "Last 24h", "Last 48h", "All"],
        index=3,
        help="Show only log entries within this window. Requires server logs with timestamps.",
    )
    log_category = st.selectbox(
        "Category",
        ["All logs", "Dropped & validation only"],
        help="Dropped & validation: magic word, checksum, size mismatch, listener errors.",
    )
    log_lines = st.slider("Log lines to show (full log tabs)", min_value=10, max_value=500, value=100, step=10)

# --- Main: Header ---
st.markdown('<p class="main-title">ASE Traffic Control Plane</p>', unsafe_allow_html=True)
st.caption("Real-time statistics and detailed logs — run server and monitor in the terminal")


def format_bytes(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


@st.fragment(run_every=2)
def live_metrics_and_log():
    """Refreshes every 2s: shared-memory metrics, throughput rates, per-worker throughput, log tail."""
    stats = read_shm_stats()
    rates = compute_rates(stats)
    dropped = stats["dropped_packets"] if stats else 0

    # --- Cumulative statistics (counters) ---
    st.markdown("#### Counters")
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        val = stats["packets_processed"] if stats else 0
        st.metric("Total Packets Processed", f"{val:,}")
    with m2:
        st.metric(
            "Dropped Packets",
            f"{dropped:,}",
            delta=f"+{dropped}" if dropped > 0 else None,
            delta_color="inverse",
        )
    with m3:
        bytes_val = stats["bytes_transferred"] if stats else 0
        st.metric("Bytes Transferred", format_bytes(bytes_val))
    with m4:
        uptime = uptime_str(stats["start_time_sec"], stats["is_running"]) if stats else "—"
        st.metric("Uptime", uptime)
    with m5:
        status = "Running" if (stats and stats["is_running"]) else "Stopped"
        st.metric("Status", status)

    # --- Throughput (rates) — industry-standard traffic view ---
    st.markdown("#### Throughput (rates)")
    r1, r2, r3, r4 = st.columns(4)
    with r1:
        st.metric("Packets/s", f"{rates['packets_per_sec']:.1f}")
    with r2:
        st.metric("Bytes/s", format_bytes(rates["bytes_per_sec"]))
    with r3:
        st.metric("Drops/s", f"{rates['drops_per_sec']:.2f}")
    with r4:
        drop_pct = rates["drop_pct"]
        st.metric("Drop rate %", f"{drop_pct:.2f}%", delta=None if drop_pct == 0 else f"{drop_pct:.2f}%", delta_color="inverse")

    if dropped > 0:
        st.markdown(
            '<p class="delta-bad">⚠ Dropped packets detected — check magic word / checksum in logs.</p>',
            unsafe_allow_html=True,
        )

    raw_load = (stats["thread_load"] if stats else None) or []
    thread_load = (list(raw_load) + [0] * 4)[:4]
    worker_pps = rates["worker_pps"]
    max_pps = max(worker_pps) or 1
    cv = rates["load_balance_cv"]

    # --- Worker cards: cumulative count + throughput (p/s) and bar = throughput vs max ---
    st.markdown("#### Worker throughput (packets/sec)")
    w1, w2, w3, w4 = st.columns(4)
    for col, i in [(w1, 0), (w2, 1), (w3, 2), (w4, 3)]:
        with col:
            pps = worker_pps[i]
            bar_pct = min(100, round(100 * pps / max_pps))
            st.markdown(
                f'<div class="worker-card">'
                f'<div class="worker-name">Worker {i+1}</div>'
                f'<div class="worker-value">{pps:.1f} <span style="font-size:0.75rem;color:#86868b;">p/s</span></div>'
                f'<div class="worker-util">Total: {thread_load[i]:,} packets</div>'
                f'<div class="worker-bar-track">'
                f'<div class="worker-bar-fill w{i+1}" style="width:{bar_pct}%"></div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

    # --- Bar visualisation: throughput (p/s) per worker — same scale (0 to max), not % of total ---
    st.markdown("#### Throughput distribution (p/s per worker, same scale)")
    chart_html = '<div style="margin-top:0.5rem;">'
    for i in range(4):
        pps = worker_pps[i]
        bar_pct = min(100, (100 * pps / max_pps) if max_pps else 0)
        chart_html += (
            f'<div class="chart-row">'
            f'<span class="chart-label">Worker {i+1}</span>'
            f'<div class="chart-bar-wrap">'
            f'<div class="chart-bar worker-bar-fill w{i+1}" style="width:{bar_pct}%"></div>'
            f'</div>'
            f'<span class="chart-val">{pps:.1f} p/s</span>'
            f'</div>'
        )
    chart_html += '</div>'
    st.markdown(chart_html, unsafe_allow_html=True)

    # --- Load balance indicator (industry: CV &lt; 0.2 = balanced) ---
    balance_class = "balance-ok" if cv < 0.2 else ("balance-warn" if cv < 0.5 else "balance-bad")
    balance_label = "Balanced" if cv < 0.2 else ("Moderate skew" if cv < 0.5 else "Skewed")
    st.markdown(
        f'<p class="section-label">Load balance <span class="{balance_class}">● {balance_label}</span> (CV={cv:.2f})</p>',
        unsafe_allow_html=True,
    )

    # --- Throughput over time (sparkline) ---
    hist = st.session_state.get("throughput_history", [])
    if len(hist) >= 2:
        values = [v for _, v in hist]
        mx = max(values) or 1
        mn = min(values)
        current = values[-1]
        n = len(values) - 1
        points = " ".join(f"{i * 100 / n:.1f},{30 - (v / mx) * 27:.1f}" for i, v in enumerate(values))
        window_sec = 2 * len(values)  # 1 sample every 2s
        st.markdown(
            f'<p class="section-label">Throughput (packets/s) over time</p>'
            f'<p style="font-size:0.8rem;color:#86868b;margin-bottom:0.35rem;">'
            f'Y-axis: packets/s (global). X-axis: time, oldest ← left, newest → right. '
            f'Window: last {len(values)} samples (≈{window_sec}s at 2s refresh).</p>'
            f'<div class="sparkline-wrap">'
            f'<svg viewBox="0 0 100 30" preserveAspectRatio="none" style="width:100%;height:36px;display:block;">'
            f'<polyline fill="none" stroke="rgba(48,209,88,0.8)" stroke-width="0.5" points="{points}"/>'
            f'</svg>'
            f'<div style="display:flex;gap:1.25rem;font-size:0.8rem;color:#a1a1a6;margin-top:0.35rem;">'
            f'<span><strong style="color:#f5f5f7;">Current:</strong> {current:.1f} p/s</span>'
            f'<span><strong style="color:#f5f5f7;">Min:</strong> {mn:.1f} p/s</span>'
            f'<span><strong style="color:#f5f5f7;">Max:</strong> {mx:.1f} p/s</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    # --- Log filters: cutoff for time range (seconds ago); None = All ---
    time_cutoff_sec = {"Last 1h": 3600, "Last 6h": 21600, "Last 24h": 86400, "Last 48h": 172800}.get(
        time_range
    )
    cutoff_epoch = (time.time() - time_cutoff_sec) if time_cutoff_sec else None

    def keep_time(epoch):
        if cutoff_epoch is None:
            return True
        if epoch is None:
            return True  # no timestamp: include (e.g. client log or old server lines)
        return epoch >= cutoff_epoch

    st.markdown("#### Logs (detailed)")
    server_entries = read_log_with_timestamps(SERVER_LOG)
    drop_entries = [
        (ts, line)
        for ts, line in server_entries
        if keep_time(ts) and any(p in line for _, p in DROP_VALIDATION_PATTERNS)
    ]

    def render_dropped_view():
        if not drop_entries:
            st.markdown(
                '<div class="log-box" style="color:#86868b;">No dropped or validation-failure entries in the selected time range. Run server with stderr to file (e.g. <code>./server 2&gt;&amp;1 | tee server.log</code>) so timestamps appear.</div>',
                unsafe_allow_html=True,
            )
        else:
            cards_html = []
            for ts, line in drop_entries:
                tag, _ = tag_drop_line(line)
                reason, details = parse_drop_reason_and_details(line)
                tag_badge = (
                    f'<span class="log-tag log-tag-{tag.lower()}">{tag}</span> '
                    if tag
                    else ""
                )
                ts_str = f"[{datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC] " if ts else ""
                reason_esc = html.escape(reason)
                details_html = ""
                if details:
                    details_parts = [f'<span><kbd>{html.escape(k)}</kbd> {html.escape(str(v))}</span>' for k, v in details]
                    details_html = f'<div class="drop-details">{" ".join(details_parts)}</div>'
                raw_esc = html.escape(ts_str + line)
                cards_html.append(
                    f'<div class="drop-card">'
                    f'<div class="drop-reason">{tag_badge}{reason_esc}</div>'
                    f'{details_html}'
                    f'<div class="drop-raw">{raw_esc}</div>'
                    f'</div>'
                )
            st.markdown(
                f'<div class="log-box log-box-drops">{"".join(cards_html)}</div>',
                unsafe_allow_html=True,
            )
        st.caption(
            "Each entry shows: reason, expected/received details, and the raw server log line."
        )

    if log_category == "Dropped & validation only":
        render_dropped_view()
    else:
        tab_server, tab_client, tab_drops = st.tabs(
            ["Server log", "Client log", "Dropped & validation"]
        )
        with tab_server:
            filtered_server = [(ts, line) for ts, line in server_entries if keep_time(ts)]
            display_lines = []
            for ts, line in filtered_server[-log_lines:]:
                ts_str = f"[{datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%H:%M:%S')}Z] " if ts else ""
                display_lines.append(ts_str + line)
            log_content = html.escape("\n".join(display_lines)) if display_lines else "(no server log or no entries in time range)"
            st.markdown(f'<div class="log-box">{log_content}</div>', unsafe_allow_html=True)
        with tab_client:
            client_entries = read_log_with_timestamps(CLIENT_LOG)
            filtered_client = [(ts, line) for ts, line in client_entries if keep_time(ts)]
            display_lines = []
            for ts, line in filtered_client[-log_lines:]:
                ts_str = f"[{datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%H:%M:%S')}Z] " if ts else ""
                display_lines.append(ts_str + line)
            client_content = html.escape("\n".join(display_lines)) if display_lines else "(no client log or no entries in time range)"
            st.markdown(f'<div class="log-box">{client_content}</div>', unsafe_allow_html=True)
        with tab_drops:
            render_dropped_view()


live_metrics_and_log()

st.markdown("---")
st.caption("Dashboard refreshes every 2s. Throughput rates and load balance are derived from deltas. Run ./server, ./monitor, and python client.py in separate terminals.")
