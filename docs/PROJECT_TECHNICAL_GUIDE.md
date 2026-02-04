# UDP Multi-Threaded Packet Processor — Complete Technical Guide

A comprehensive guide to understand every component of this project and answer technical interview questions.

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Packet Processing Flow](#2-packet-processing-flow)
3. [Validation Order in process_packet](#3-validation-order-in-process_packet)
4. [Producer–Consumer Synchronization](#4-producerconsumer-synchronization)
5. [File-by-File Breakdown](#5-file-by-file-breakdown)
6. [Interview Q&A Cheat Sheet](#6-interview-qa-cheat-sheet)

---

## 1. System Architecture Overview

**Visual: System architecture — components and data flow**

```
┌─────────────────┐     UDP      ┌──────────────────────────────────────────────────────────┐
│  Client         │ ──────────►  │  Server process (C++)                                    │
│  (Python)       │              │                                                          │
└─────────────────┘              │  ┌──────────────────┐      ┌─────────────────────────┐   │
                                 │  │ Listener thread  │ ───► │ Queue (mutex + CV)     │   │
                                 │  │ recvfrom         │      │ g_packet_queue         │   │
                                 │  └──────────────────┘      └───────────┬─────────────┘   │
                                 │                                        │                 │
                                 │           ┌────────────────────────────┼──────────────┐  │
                                 │           │                            │              │  │
                                 │           ▼                            ▼              ▼  │
                                 │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
                                 │  │ Worker 1   │ │ Worker 2   │ │ Worker 3   │ │ Worker 4   │
                                 │  │process_pkt │ │process_pkt │ │process_pkt │ │process_pkt │
                                 │  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
                                 │        └──────────────┴──────────────┴──────────────┘   │
                                 │                        │                                │
                                 │                        ▼                                │
                                 │           ┌─────────────────────────┐                   │
                                 │           │ POSIX shared memory     │ ◄── writes        │
                                 │           │ (stats)                 │                   │
                                 │           └────────────┬────────────┘                   │
                                 └────────────────────────┼────────────────────────────────┘
                                                          │
                        ┌─────────────────────────────────┼─────────────────────────────────┐
                        │ read                             │ read                            │
                        ▼                                 ▼                                 │
               ┌────────────────┐              ┌────────────────────┐                       │
               │ Monitor (C++)  │              │ Dashboard (Python) │                       │
               └────────────────┘              └────────────────────┘                       │
```

### Key Components

| Component | Language | Role |
|-----------|----------|------|
| **Client** | Python | Generates and sends UDP packets at configurable rate |
| **Server** | C++ | Receives packets, validates, decrypts, processes; writes stats to shared memory |
| **Listener thread** | C++ | Dedicated thread that calls `recvfrom` on the UDP socket |
| **Queue** | C++ | Thread-safe buffer using mutex + condition variable (producer-consumer) |
| **Worker threads** | C++ | Four threads that `pop_packet` from queue and call `process_packet` |
| **POSIX shared memory** | — | Named segment `/dev/shm/telecom_shm` holding `SystemStats` |
| **Monitor** | C++ | Separate process reading stats from shared memory; displays live throughput |
| **Dashboard** | Python | Streamlit app reading stats and logs; visual metrics + worker load chart |

### Data Flow Summary

1. **Client → Server:** UDP packets over port 8080
2. **Listener → Queue:** `recvfrom` → copy → `push_packet` (producer)
3. **Queue → Workers:** `pop_packet` → `process_packet` (consumers)
4. **Server → Shared memory:** Workers update `g_stats` (packets, bytes, dropped, thread_load)
5. **Shared memory → Monitor / Dashboard:** Read-only mapping; no network or disk I/O

---

## 2. Packet Processing Flow

**Visual: Packet processing flow — from socket to process**

```
 recvfrom          copy          push_packet        Queue          pop_packet       process_packet
 (Listener)                      (shared)           (mutex+CV)                      (Worker)
     │                               │                   │                              │
     ▼                               ▼                   ▼                              ▼
┌─────────┐     ┌─────────┐     ┌─────────┐       ┌──────────┐     ┌─────────┐     ┌──────────────┐
│ Receive │ ──► │ Copy to │ ──► │ Add to  │ ────► │ Shared   │ ──► │ Pop one │ ──► │ Validate,    │
│ packet  │     │ heap    │     │ queue   │       │ queue    │     │ packet  │     │ decrypt,     │
│ from    │     │ buffer  │     │         │       │          │     │         │     │ update stats │
│ socket  │     │         │     │         │       │          │     │         │     │              │
└─────────┘     └─────────┘     └─────────┘       └──────────┘     └─────────┘     └──────────────┘
```

### Step-by-Step

| Step | Function | Thread | Purpose |
|------|----------|--------|---------|
| 1 | `recvfrom` | Listener | Receive UDP datagram into stack buffer |
| 2 | `copy` | Listener | Allocate heap buffer, `memcpy` packet; listener can immediately read next packet |
| 3 | `push_packet` | Listener | Lock mutex, push `{ptr, len}` to queue, `notify_one()` |
| 4 | Queue | Shared | Holds packets; protected by `g_queue_mutex` and `g_queue_cv` |
| 5 | `pop_packet` | Worker | Wait on CV until queue non-empty or shutdown; pop one packet |
| 6 | `process_packet` | Worker | Validate (size, header, magic, length, checksum), decrypt, update stats |

### Why Copy?

The listener uses a **single stack buffer** for `recvfrom`. Copying to the heap before pushing ensures:

- Workers get their own buffer; no race with the next `recvfrom`
- Listener can immediately return to receiving without waiting for processing
- Decouples high-speed reception from potentially slower validation/decryption

---

## 3. Validation Order in process_packet

**Visual: Validation order — strict order before trusting payload**

```
Start
  │
  ▼
1. Size cap check ─────────────────────────────────────┐
  │ (bytes_received > MAX_BUFFER_SIZE?)                 │
  │                                                    │ fail → drop
  ▼ pass                                               │
2. Min size ≥ header? ─────────────────────────────────┤
  │ (bytes_received >= sizeof(PacketHeader)?)           │
  │                                                    │
  ▼ pass                                               │
3. Parse header (ntohl / ntohs)                         │
  │                                                    │
  ▼                                                    │
4. Magic word OK? (0xDEADBEEF)                         │
  │                                                    │
  ▼                                                    │
5. Length consistent?                                   │
  │ (bytes_received >= header + payload_len)            │
  │                                                    │
  ▼                                                    │
6. Checksum OK?                                        │
  │                                                    │
  ▼                                                    ▼
7. Decrypt & update stats                        dropped_packets++
```

### Strict Order Rationale

We **never** trust or process the payload until all validations pass. Order matters:

1. **Size cap** — Prevents buffer overflow and resource exhaustion
2. **Min size ≥ header** — Ensures we can safely parse the header (avoid out-of-bounds read)
3. **Parse header** — Extract `magic_word`, `payload_len`, `checksum` in network byte order
4. **Magic word** — Quick rejection of non-protocol or spoofed packets
5. **Length consistent** — Header says N bytes; we must have received at least N
6. **Checksum** — Integrity check; rejects corrupted or tampered data
7. **Decrypt & update stats** — Only after all checks pass; increment `packets_processed`, etc.

On any failure (2–6): increment `dropped_packets`, return, do **not** decrypt or update processed counts.

---

## 4. Producer–Consumer Synchronization

**Visual: Mutex and condition variable**

```
┌──────────────────────────────────────────────────────────────────────┐
│ Listener (Producer)                                                  │
│   lock (lock_guard) → push → notify_one()                            │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Shared resources                                                     │
│   g_queue_mutex   — protects g_packet_queue                          │
│   g_queue_cv      — signals "queue not empty"                        │
│   g_packet_queue  — std::queue<pair<uint8_t*, size_t>>               │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Workers (Consumers)                                                  │
│   wait(lock, predicate) — unique_lock; predicate: !empty || !running │
│   pop when woken                                                     │
└──────────────────────────────────────────────────────────────────────┘
```

### Synchronization Primitives

| Primitive | Used By | Purpose |
|-----------|---------|---------|
| `std::mutex g_queue_mutex` | Both | Protect `g_packet_queue` from concurrent access |
| `std::condition_variable g_queue_cv` | Both | Workers block until queue has work or shutdown |
| `std::atomic<bool> g_running` | Main + workers | Graceful shutdown; workers exit when false |
| `std::lock_guard` | Producer (`push_packet`) | Short critical section; auto unlock |
| `std::unique_lock` | Consumers (`pop_packet`) | Required for `cv.wait()`; supports unlock/relock |

### Producer (push_packet)

```cpp
void push_packet(uint8_t* data, size_t len) {
    std::lock_guard<std::mutex> lock(g_queue_mutex);  // Lock
    uint8_t* packet = new uint8_t[len];
    memcpy(packet, data, len);
    g_packet_queue.push({packet, len});
    g_queue_cv.notify_one();  // Wake one worker
}
```

- **Why `lock_guard`?** Short critical section; no need to wait or release early
- **Why `notify_one()`?** One new packet → wake one worker; avoids thundering herd

### Consumer (pop_packet)

```cpp
bool pop_packet(uint8_t*& data, size_t& len) {
    std::unique_lock<std::mutex> lock(g_queue_mutex);
    g_queue_cv.wait(lock, [] { return !g_packet_queue.empty() || !g_running; });
    if (!g_running && g_packet_queue.empty()) return false;
    auto pair = g_packet_queue.front();
    g_packet_queue.pop();
    data = pair.first;
    len = pair.second;
    return true;
}
```

- **Why `unique_lock`?** `condition_variable::wait()` must unlock while waiting; only `unique_lock` supports that
- **Predicate:** Avoids spurious wakeups; wake when queue non-empty **or** shutdown
- **Shutdown:** `g_running = false` + `notify_all()` → all workers wake, see empty queue, return false, exit

---

## 5. File-by-File Breakdown

### protocol.h

**Purpose:** Single source of truth for packet layout and shared-memory layout. Used by server, monitor, and (logically) client and dashboard.

**Contents:**

- **SHM_NAME, SHM_SIZE** — POSIX shared memory name and size
- **PacketHeader** — `__attribute__((packed))` 12-byte header:
  - `magic_word` (4B), `seq_num` (2B), `payload_len` (2B), `checksum` (4B)
- **SystemStats** — Shared stats struct:
  - `packets_processed`, `bytes_transferred`, `dropped_packets`
  - `start_time_sec`, `is_running`, padding, `thread_load[4]`

**Why packed?** No padding; layout matches wire format and is identical across compilers.

---

### server.cpp

**Purpose:** Multi-threaded UDP server: receive, validate, decrypt, process packets; expose stats via shared memory.

**Main sections:**

| Lines | Section | Description |
|-------|---------|-------------|
| 24–37 | Constants, globals | `UDP_PORT`, `MAX_BUFFER_SIZE`, `NUM_WORKER_THREADS`, queue, mutex, CV, `g_stats` |
| 39–60 | Queue ops | `push_packet` (producer), `pop_packet` (consumer) |
| 63–76 | Helpers | `calculate_checksum`, `decrypt_payload` (XOR) |
| 78–156 | process_packet | Validation (size, header, magic, length, checksum), decrypt, update stats |
| 158–174 | worker_thread | Loop: `pop_packet` → `process_packet` → `delete[]` |
| 176–206 | listener_thread | Loop: `recvfrom` → `push_packet` |
| 208–265 | Shared memory | `setup_shared_memory`, `cleanup_shared_memory` |
| 267–295 | Setup | Signal handlers, UDP socket (non-blocking), bind |
| 297–339 | main | Start workers, listener; join; cleanup |

**Key design choices:**

- Non-blocking socket: `fcntl(O_NONBLOCK)` so `recvfrom` doesn’t block on empty socket
- Four worker threads: configurable via `NUM_WORKER_THREADS`
- Graceful shutdown: SIGINT/SIGTERM sets `g_running = false`, `notify_all()`, workers exit

---

### monitor.cpp

**Purpose:** Separate C++ process that reads `SystemStats` from shared memory and prints live throughput.

**Main sections:**

| Lines | Section | Description |
|-------|---------|-------------|
| 49–66 | Setup | `shm_open(O_RDONLY)`, `mmap(PROT_READ)` |
| 74–111 | Loop | Every 1s: compute packets/sec and bytes/sec deltas, format and print |
| 26–39 | format_bytes | Human-readable B/KB/MB/GB |

**Why separate process?** Observability without adding I/O or locks to the server hot path.

---

### client.py

**Purpose:** Generate and send UDP packets conforming to the custom protocol.

**Main sections:**

| Section | Description |
|---------|-------------|
| Protocol constants | `MAGIC_WORD`, `UDP_PORT`, `ENCRYPTION_KEY` (must match server) |
| create_packet | Build header + encrypted payload; checksum over bytes 0–7 and 12–end |
| send_packets | Rate-limited send loop; logs to `client.log` |
| CLI | `--host`, `--port`, `--rate`, `--duration`, `--payload-size` |

**Checksum:** Sum of all bytes except the 4-byte checksum field; same algorithm as server.

---

### dashboard.py

**Purpose:** Streamlit dashboard for real-time metrics and log tails.

**Main sections:**

| Section | Description |
|---------|-------------|
| read_shm_stats | Open `/dev/shm/telecom_shm`, mmap read-only, unpack `SystemStats` with `struct.unpack` |
| tail_log | Read last N lines from `server.log` and `client.log` |
| live_metrics_and_log | `@st.fragment(run_every=2)` — refresh every 2s; show packets, dropped, bytes, uptime, status |
| Worker load | Per-thread packet counts, utilisation %, bar chart |

**Layout:** Must match `protocol.h`; `STATS_STRUCT_FMT = "<QQQQB7x4Q"` aligns with `SystemStats`.

---

### Makefile

**Purpose:** Build server and monitor.

**Targets:**

- `all` (default): Build `server` and `monitor`
- `clean`: Remove binaries
- `run-server`, `run-monitor`: Convenience run targets

**Flags:** `-std=c++11 -Wall -Wextra -O2 -pthread -lrt` (lrt for POSIX shm).

---

### run_demo.sh

**Purpose:** End-to-end demo script.

**Steps:** Build → clean old shm → start server → start monitor → run client 10s → stop server/monitor.

---

### requirements-dashboard.txt

**Purpose:** Python dependencies for dashboard (Streamlit).

---

## 6. Interview Q&A Cheat Sheet

### Concurrency

**Q: Describe the threading model.**  
One listener (producer) and four workers (consumers) share a mutex-protected queue. Workers block on a condition variable until the queue is non-empty or shutdown. Predicate in `wait` avoids spurious wakeups and enables clean exit.

**Q: Why mutex + condition variable instead of a lock-free queue?**  
A lock-based queue with a condition variable is standard, correct, and easy to reason about. Lock-free queues help at very high throughput but add complexity; for this project, correctness and clarity matter more.

**Q: Why copy the packet before pushing?**  
The listener reuses a single stack buffer. Copying ensures workers get their own buffer and the listener can immediately receive the next packet without races.

**Q: Why `lock_guard` for producer and `unique_lock` for consumer?**  
Producer: short critical section, no wait. Consumer: `condition_variable::wait()` must unlock while waiting; only `unique_lock` supports that.

---

### Protocol & Data Integrity

**Q: How do you handle endianness?**  
Client sends in network byte order (big-endian). Server uses `ntohl`/`ntohs` on multi-byte header fields before use, so the protocol works on any host endianness.

**Q: What is the validation order and why?**  
Size cap → min size ≥ header → parse header → magic word → length consistency → checksum. Only then decrypt and update stats. We never trust the payload before all checks pass.

**Q: How is the checksum computed?**  
Sum of all bytes except the 4-byte checksum field (bytes 0–7 and 12–end), masked to 32 bits. Same on client and server.

---

### IPC & Monitoring

**Q: Why POSIX shared memory for stats?**  
Zero-copy: server writes into the same region monitor/dashboard map read-only. No serialization, no network or disk I/O. Fixed layout, predictable, Linux-friendly.

**Q: Does the dashboard affect P99 latency?**  
No. Dashboard and monitor are separate processes that only read shared memory. The server does not perform RPC or extra I/O for them; it only updates in-memory counters.

---

### Code Locations Quick Reference

| Topic | File | Lines |
|-------|------|-------|
| Queue, mutex, CV | server.cpp | 33–35, 39–60 |
| push_packet / pop_packet | server.cpp | 39–60 |
| Worker loop, shutdown | server.cpp | 163–174, 258–264 |
| PacketHeader, SystemStats | protocol.h | 13–30 |
| Endianness (ntohl/ntohs) | server.cpp | 101–105 |
| Checksum verification | server.cpp | 127–139 |
| Validation order | server.cpp | 80–139 |
| Shared memory setup | server.cpp | 210–256 |
| Monitor reading shm | monitor.cpp | 49–66, 80–83 |
| Dashboard reading shm | dashboard.py | 27–46 |

---

*Use this guide together with the architecture diagrams to prepare for technical deep dives.*
