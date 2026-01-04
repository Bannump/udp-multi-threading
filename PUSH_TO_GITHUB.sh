#!/bin/bash
# Commands to push local repository to GitHub

# Navigate to project directory
cd /mnt/c/Users/sarat/OneDrive/Documents/Coding/networking_venkata_naveen

# Check if git is initialized
if [ ! -d .git ]; then
    echo "Initializing git repository..."
    git init
fi

# Check current remotes
echo "Current remotes:"
git remote -v

# Add the GitHub remote (if not already added)
echo ""
echo "Adding remote origin..."
git remote remove origin 2>/dev/null  # Remove if exists
git remote add origin https://github.com/Bannump/udp-multi-threading.git

# Verify remote
echo ""
echo "Updated remotes:"
git remote -v

# Check current branch
echo ""
echo "Current branch:"
git branch

# Add all files
echo ""
echo "Adding files..."
git add .

# Check status
echo ""
echo "Git status:"
git status

# Create commit if needed
echo ""
read -p "Do you want to commit changes? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    git commit -m "Initial commit: Secure Multi-Threaded UDP Packet Processor with IPC Monitoring"
fi

# Push to GitHub
echo ""
echo "Pushing to GitHub..."
echo "Note: If the repository is empty, use 'git push -u origin main' or 'git push -u origin master'"
echo ""

# Try to determine default branch
if git branch | grep -q "main"; then
    git branch -M main
    git push -u origin main
elif git branch | grep -q "master"; then
    git push -u origin master
else
    echo "No main or master branch found. Creating main branch..."
    git branch -M main
    git push -u origin main
fi

echo ""
echo "Done! Check your repository at: https://github.com/Bannump/udp-multi-threading"

