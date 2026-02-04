#!/usr/bin/env python3
"""
ASE Traffic Control Plane — Streamlit Monitoring Dashboard
Real-time statistics and detailed logs for the C++ UDP Packet Processor.
Run server and monitor manually in the terminal; use this for metrics + log view.
"""

import html
import struct
import mmap
import time
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
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Sidebar: info only ---
with st.sidebar:
    st.markdown("### Info")
    st.markdown("Run **server**, **monitor**, and **client** in separate terminals. This dashboard shows live statistics and server/client log tails.")
    st.markdown("---")
    log_lines = st.slider("Log lines to show", min_value=10, max_value=100, value=50, step=10)

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
    """Refreshes every 2s: shared-memory metrics, thread load chart, log tail."""
    stats = read_shm_stats()
    dropped = stats["dropped_packets"] if stats else 0

    st.markdown("#### Statistics")
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

    if dropped > 0:
        st.markdown(
            '<p class="delta-bad">⚠ Dropped packets detected — check magic word / checksum in logs.</p>',
            unsafe_allow_html=True,
        )

    total_packets = (stats["packets_processed"] if stats else 0) or 1
    st.markdown("#### Worker thread load (packets per thread)")
    raw_load = (stats["thread_load"] if stats else None) or []
    thread_load = (list(raw_load) + [0] * 4)[:4]  # pad to 4, avoid IndexError
    max_load = max(thread_load) or 1
    w1, w2, w3, w4 = st.columns(4)
    for col, i in [(w1, 0), (w2, 1), (w3, 2), (w4, 3)]:
        with col:
            val = thread_load[i]
            util_pct = (100 * val / total_packets) if total_packets else 0
            bar_pct_rel = min(100, round(100 * val / max_load))  # bar vs max for balance
            st.markdown(
                f'<div class="worker-card">'
                f'<div class="worker-name">Worker {i+1}</div>'
                f'<div class="worker-value">{val:,}</div>'
                f'<div class="worker-util">Utilisation: ~{util_pct:.2f}%</div>'
                f'<div class="worker-bar-track">'
                f'<div class="worker-bar-fill w{i+1}" style="width:{bar_pct_rel}%"></div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
    # Summary bar chart with same thread colors (% of total packets)
    chart_html = '<div style="margin-top:0.5rem;">'
    for i in range(4):
        val = thread_load[i]
        util_pct = (100 * val / total_packets) if total_packets else 0
        bar_pct = min(100, util_pct)  # bar width = share of total (sum ≈ 100%)
        chart_html += (
            f'<div class="chart-row">'
            f'<span class="chart-label">Worker {i+1}</span>'
            f'<div class="chart-bar-wrap">'
            f'<div class="chart-bar worker-bar-fill w{i+1}" style="width:{bar_pct}%"></div>'
            f'</div>'
            f'<span class="chart-val">{val:,} (~{util_pct:.2f}%)</span>'
            f'</div>'
        )
    chart_html += '</div>'
    st.markdown(chart_html, unsafe_allow_html=True)

    st.markdown("#### Logs (detailed)")
    tab_server, tab_client = st.tabs(["Server log", "Client log"])
    with tab_server:
        log_content = html.escape(tail_log(SERVER_LOG, log_lines))
        st.markdown(f'<div class="log-box">{log_content}</div>', unsafe_allow_html=True)
    with tab_client:
        client_content = html.escape(tail_log(CLIENT_LOG, log_lines))
        st.markdown(f'<div class="log-box">{client_content}</div>', unsafe_allow_html=True)


live_metrics_and_log()

st.markdown("---")
st.caption("Dashboard refreshes every 2s. Run ./server, ./monitor, and python client.py in separate terminals. Server log: server.log; client log: client.log.")
