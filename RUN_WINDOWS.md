# Running on Windows

This project uses POSIX APIs (sockets, shared memory, pthreads), so run it **inside WSL** (Windows Subsystem for Linux). You have Ubuntu installed; use it.

## One-time: build

In a terminal (PowerShell or WSL), from the project folder:

```powershell
wsl -d Ubuntu -e bash -c "cd '/mnt/c/Users/sarat/OneDrive/Documents/self_learning/udp-multi-threading' && make"
```

Or open **WSL (Ubuntu)** and run:

```bash
cd /mnt/c/Users/sarat/OneDrive/Documents/self_learning/udp-multi-threading
make
```

## Run the app (3 terminals)

Use **three** WSL Ubuntu terminals (or `wsl -d Ubuntu` three times).

### Terminal 1 – Server

```bash
cd /mnt/c/Users/sarat/OneDrive/Documents/self_learning/udp-multi-threading
./server
```

Leave it running. It binds to UDP port 8080 and starts worker threads.

### Terminal 2 – Monitor

```bash
cd /mnt/c/Users/sarat/OneDrive/Documents/self_learning/udp-multi-threading
./monitor
```

Leave it running. It shows live stats from the server via shared memory.

### Terminal 3 – Python client

```bash
cd /mnt/c/Users/sarat/OneDrive/Documents/self_learning/udp-multi-threading
python3 client.py --rate 2000 --duration 10
```

Options: `--rate` (packets/sec), `--duration` (seconds), `--payload-size`, `--host`, `--port`.

## Quick one-shot demo (PowerShell)

Build, start server and monitor, run client 5 seconds, then stop:

```powershell
cd "c:\Users\sarat\OneDrive\Documents\self_learning\udp-multi-threading"
wsl -d Ubuntu -e bash -c "cd '/mnt/c/Users/sarat/OneDrive/Documents/self_learning/udp-multi-threading' && make clean && make && rm -f /dev/shm/telecom_shm 2>/dev/null; ./server & SPID=\$!; sleep 2; ./monitor & MPID=\$!; sleep 1; python3 client.py --rate 2000 --duration 5; kill \$SPID \$MPID 2>/dev/null; echo Done."
```

## Troubleshooting

- **Port 8080 in use:** In WSL run `sudo lsof -i :8080` (or `ss -tulnp | grep 8080`) to find the process, then `kill <PID>`.
- **Stale shared memory:** In WSL run `sudo rm -f /dev/shm/telecom_shm`.
- **`make` not found in WSL:** Install build-essential: `sudo apt update && sudo apt install -y build-essential`.
- **`streamlit: command not found`:** Use the venv: `source .venv/bin/activate` then `pip install -r requirements-dashboard.txt` and `streamlit run dashboard.py`.
- **pip "Invalid requirement" for a file:** Use `-r`: `pip install -r requirements-dashboard.txt`.
