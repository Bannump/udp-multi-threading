# Deploying the showcase and running the demo

This guide is for **you (the project author)**. It explains how to put the project on the internet and how **only you** can start the server, while others can test it when you have the server running.

## 1. Enable the showcase site (GitHub Pages)

The showcase site lives in the `docs/` folder and is served by GitHub Pages.

1. Open your repo: **https://github.com/Bannump/udp-multi-threading**
2. Go to **Settings** → **Pages** (under "Code and automation").
3. Under **Build and deployment** → **Source**, choose **Deploy from a branch**.
4. Under **Branch**, pick your branch (e.g. `main` or `version2.2`) and set the folder to **/docs**.
5. Save. After a minute or two the site will be at:
   - **https://bannump.github.io/udp-multi-threading/**

Visitors will see the project overview and a **Live demo** section. That section shows connection details only when you have set the demo as "online" (see below). There is **no button or way for anyone else to start the server** — only you start it on your machine or VPS.

---

## 2. How “only you start the server” works

- The **server binary** runs only where **you** run it (your PC, WSL, or a VPS you control).
- The showcase website does **not** start or stop the server. It only shows connection info when you say the demo is online.
- You turn the demo “on” or “off” by editing `docs/demo-config.json` and pushing to GitHub (see below).

So: **nobody on the internet can start your server**; they can only connect to it when **you** have started it and published the connection details.

---

## 3. When you want to run the demo (so others can test)

Pick one of the two options below. In both cases you will later update `docs/demo-config.json` so the showcase page shows the correct host/port.

### Option A: Run the server on a VPS (simplest for UDP)

1. Create a small Linux VPS (e.g. Ubuntu on DigitalOcean, Linode, or any provider) with a **public IP**.
2. On the VPS: clone the repo, install build deps, then:
   ```bash
   make
   ./server
   ```
3. The server listens on UDP port **8080**. Ensure the VPS firewall allows **UDP 8080** from the internet.
4. Your “demo host” is the VPS public IP (e.g. `203.0.113.10`). Port is `8080` unless you changed it.

### Option B: Run the server locally and expose it with a UDP tunnel

Because the app uses **UDP**, normal HTTP tunnels (e.g. default ngrok) are not enough. Use a tunnel that supports UDP:

- **Pinggy** (UDP support): https://pinggy.io/  
  Example (after installing their client): expose UDP from your machine to the internet and use the host they give you.
- **Cloudflare Tunnel (cloudflared)** can proxy UDP in some setups; see Cloudflare’s docs for UDP.

Run your server locally (e.g. in WSL):

```bash
make
./server
```

Then start the tunnel so that the **public host:port** forwards UDP to `localhost:8080`. Use that public host (and port if different) as the demo address.

---

## 4. Tell the showcase that the demo is “online”

When the server is running and reachable (VPS IP or tunnel host/port), update the config that the showcase page reads:

1. Edit **`docs/demo-config.json`** in your repo:

   **When the demo is running:**

   ```json
   {
     "demo_online": true,
     "host": "YOUR_PUBLIC_HOST",
     "port": 8080,
     "note": "Only the project author can start the server. When the demo is running, connection details appear here."
   }
   ```

   Replace `YOUR_PUBLIC_HOST` with:
   - Your VPS public IP (Option A), or  
   - The tunnel’s public hostname (Option B).  
   If your tunnel uses a different port, set `"port"` to that value.

2. **When you stop the server**, set the demo offline so visitors don’t try to connect:

   ```json
   {
     "demo_online": false,
     "host": "",
     "port": 8080,
     "note": "Only the project author can start the server. When the demo is running, connection details appear here."
   }
   ```

3. Commit and push:

   ```bash
   git add docs/demo-config.json
   git commit -m "Demo server online"   # or "Demo server offline"
   git push
   ```

After the push, the showcase page at **https://bannump.github.io/udp-multi-threading/** will show “Demo server: online” and the command to run the client when the demo is up, or “Demo server: offline” when you set `demo_online` to `false`.

---

## 5. What visitors see and do

- They open **https://bannump.github.io/udp-multi-threading/** and read the project description.
- **Live demo**:
  - If you set `demo_online: false` (or haven’t set it to `true`): they see that the demo server is offline. They **cannot** start it.
  - If you set `demo_online: true` and a valid `host` (and optional `port`): they see the connection details and a command like:
    ```bash
    python3 client.py --host YOUR_PUBLIC_HOST --port 8080 --rate 1000 --duration 15
    ```
    They can clone the repo and run that command to **test** your server while it’s running.

Summary: **only you can start the server**; the site only advertises when it’s running and how to connect.
