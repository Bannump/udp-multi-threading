# GitHub Repository Setup Commands

Run these commands in order to push your project to GitHub:

## Step 1: Initialize Git Repository

```bash
# Navigate to project directory (if not already there)
cd /mnt/c/Users/sarat/OneDrive/Documents/Coding/networking_venkata_naveen

# Initialize git repository
git init

# Configure git (if not already done globally)
git config user.name "Your Name"
git config user.email "your.email@example.com"
```

## Step 2: Add All Files

```bash
# Add all project files
git add protocol.h
git add server.cpp
git add monitor.cpp
git add client.py
git add Makefile
git add README.md
git add .gitignore
git add run_demo.sh

# Or add everything at once
git add .
```

## Step 3: Create Initial Commit

```bash
# Create initial commit
git commit -m "Initial commit: Secure Multi-Threaded UDP Packet Processor with IPC Monitoring

- UDP server with multi-threading (producer-consumer pattern)
- Packet encryption/decryption with XOR cipher
- POSIX shared memory IPC for statistics
- Python client for traffic generation
- Real-time monitoring via separate process
- Buffer overflow protection
- Custom binary protocol implementation"
```

## Step 4: Create GitHub Repository

**Option A: Using GitHub Web Interface (Recommended)**
1. Go to https://github.com/new
2. Repository name: `networking_venkata_naveen` (or your preferred name)
3. Description: "Secure Multi-Threaded UDP Packet Processor with IPC Monitoring - High-performance telecom component simulation"
4. Choose Public or Private
5. **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click "Create repository"

**Option B: Using GitHub CLI (if installed)**
```bash
gh repo create networking_venkata_naveen --public --description "Secure Multi-Threaded UDP Packet Processor with IPC Monitoring"
```

## Step 5: Add Remote and Push

```bash
# Add GitHub remote (replace USERNAME with your GitHub username)
git remote add origin https://github.com/USERNAME/networking_venkata_naveen.git

# Or if using SSH:
# git remote add origin git@github.com:USERNAME/networking_venkata_naveen.git

# Rename branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

## Step 6: Verify

Visit your repository on GitHub:
```
https://github.com/USERNAME/networking_venkata_naveen
```

## Optional: Add Topics/Tags on GitHub

After pushing, go to your repository settings and add topics like:
- `networking`
- `udp`
- `multithreading`
- `ipc`
- `cplusplus`
- `system-programming`
- `telecom`
- `packet-processing`

## Optional: Add License

If you want to add a license file:
```bash
# For MIT License (example)
curl -o LICENSE https://raw.githubusercontent.com/licenses/license-templates/master/templates/mit.txt
git add LICENSE
git commit -m "Add MIT License"
git push
```

