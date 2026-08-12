# GitHub Setup Guide for DataPilot

This guide will help you push your DataPilot project to GitHub.

## Prerequisites
- A GitHub account (create one at https://github.com if you don't have one)
- Git installed on your local machine (download from https://git-scm.com if needed)

---

## Step 1: Create a New GitHub Repository

1. Go to https://github.com and log in
2. Click the **"+"** icon in the top-right corner → **"New repository"**
3. Configure your repository:
   - **Repository name**: `DataPilot` (or your preferred name)
   - **Description**: (Optional) "AI-powered data analysis tool"
   - **Visibility**: Choose Public or Private
   - **⚠️ IMPORTANT**: Do NOT check any of the initialization options (README, .gitignore, license)
4. Click **"Create repository"**
5. Copy the repository URL (should look like: `https://github.com/YOUR_USERNAME/DataPilot.git`)

---

## Step 2: Push Your Code from Local Terminal

Open your terminal/command prompt and navigate to your DataPilot folder, then run these commands:

```bash
# Navigate to your project folder
cd C:\Users\Ankit_Johari\Downloads\GOD_POC\DataPilot

# Initialize git repository (if not already done)
git init

# Configure your git user (replace with your details)
git config user.email "your-email@example.com"
git config user.name "Ankit Johari"

# Add all files (the .gitignore file is already configured)
git add .

# Create your first commit
git commit -m "Initial commit: DataPilot project"

# Rename the branch to main (GitHub default)
git branch -M main

# Add your GitHub repository as remote (replace YOUR_USERNAME and REPO_NAME)
git remote add origin https://github.com/YOUR_USERNAME/DataPilot.git

# Push to GitHub
git push -u origin main
```

---

## Step 3: Authentication

When you run `git push`, GitHub will ask for authentication:

### Option A: Personal Access Token (Recommended)
1. Go to https://github.com/settings/tokens
2. Click **"Generate new token"** → **"Generate new token (classic)"**
3. Give it a name (e.g., "DataPilot Local")
4. Select scopes: Check **"repo"** (full control of private repositories)
5. Click **"Generate token"**
6. **Copy the token immediately** (you won't see it again!)
7. When git asks for password, paste this token

### Option B: GitHub CLI (Alternative)
If you prefer, install GitHub CLI and authenticate:
```bash
# Install from https://cli.github.com/
gh auth login
```

---

## Files That Won't Be Pushed (Protected by .gitignore)

The following files/folders are excluded from GitHub:
- `.env` (your environment variables - keep these secret!)
- `denv/` (virtual environment)
- `__pycache__/` (Python cache files)
- `node_modules/` (Node.js packages)

**⚠️ Security Note**: Never push your `.env` file to GitHub as it contains sensitive information!

---

## Verify Your Push

After pushing, go to your GitHub repository URL in a browser. You should see:
- `backend/` folder
- `frontend/` folder
- `requirements.txt`
- `.gitignore`

---

## Troubleshooting

### "Permission denied" or authentication fails
- Make sure you're using a Personal Access Token, not your GitHub password
- Check that the token has "repo" permissions

### "fatal: remote origin already exists"
```bash
git remote remove origin
git remote add origin https://github.com/YOUR_USERNAME/DataPilot.git
```

### Need to update remote URL
```bash
git remote set-url origin https://github.com/YOUR_USERNAME/DataPilot.git
```

---

## Next Steps After Successful Push

Consider adding these files to complete your repository:
1. **README.md** - Project description and setup instructions
2. **LICENSE** - Choose an appropriate license for your project
3. **requirements.txt** - Already present! ✓

---

**Created on**: 2026-08-12  
**For**: DataPilot Project
