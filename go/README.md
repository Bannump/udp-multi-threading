# Go implementation (same behavior as C++)

This directory contains a **Go version** of the UDP packet processor. You can run either the **C++** or the **Go** server and monitor; protocol and behavior are identical.

- **Same port**: UDP 8080  
- **Same protocol**: `protocol.h` layout (see `go/protocol/`)  
- **Same client**: Use `client.py` with either server  
- **Same IPC**: On Linux, shared memory `/dev/shm/telecom_shm` so the C++ monitor and dashboard work with the Go server (and vice versa)

## Quick start

### Run Go server

```bash
# From project root
go run ./go/server
```

Or build then run:

```bash
go build -o go/server/server.exe ./go/server/
./go/server/server.exe   # or on Unix: ./go/server/server
```

### Run Go monitor (Linux)

The Go monitor reads the same shared memory as the C++ monitor. Use it when the **Go server** or **C++ server** is running (on Linux):

```bash
go run ./go/monitor
```

Or:

```bash
go build -o go/monitor/monitor.exe ./go/monitor/
./go/monitor/monitor.exe
```

On non-Linux (e.g. Windows without WSL), the Go monitor reports that shared memory is not available; use the **C++ monitor** there if you have a way to run the server with shared memory (e.g. WSL).

## Switching between C++ and Go

1. **Stop** the current server (Ctrl+C).  
2. **Start** the other implementation:
   - C++: `./server` (after `make`)
   - Go: `go run ./go/server`
3. Keep using the **same** Python client and (on Linux) the same **monitor** or **dashboard**.

Only one server should listen on port 8080 at a time.

## Layout

- `go/protocol/` – Packet and stats layout (matches `protocol.h`)
- `go/server/` – UDP server (listener + worker pool, checksum, XOR decrypt, optional shm on Linux)
- `go/monitor/` – Stats reader from shared memory (Linux: `/dev/shm/telecom_shm`)

## Requirements

- Go 1.21+
- Linux for shared memory (server writes shm, monitor reads it). On Windows the Go server runs without shm; the dashboard/monitor will not see stats unless you run the server under WSL.
