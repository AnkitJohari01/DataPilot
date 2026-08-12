# Push DataPilot Code to GitHub

Your GitHub repository is ready at: **https://github.com/AnkitJohari01/DataPilot**

Since you've already created the repository with a README, follow these steps:

---

## Commands to Run in Your Local Terminal

Open your terminal/command prompt and run these commands:

```bash
# 1. Navigate to your project folder
cd C:\Users\Ankit_Johari\Downloads\GOD_POC\DataPilot

# 2. Initialize git (if not already done)
git init

# 3. Configure your git user
git config user.email "your-email@example.com"
git config user.name "Ankit Johari"

# 4. Add the GitHub remote
git remote add origin https://github.com/AnkitJohari01/DataPilot.git

# 5. Pull the existing README from GitHub
git pull origin main --allow-unrelated-histories

# 6. Add all your local files
git add .

# 7. Commit your changes
git commit -m "Add backend and frontend code"

# 8. Rename branch to main (if needed)
git branch -M main

# 9. Push your code to GitHub
git push -u origin main
```

---

## Authentication

When you run `git push`, GitHub will ask for credentials:

### Use Personal Access Token:
1. Username: `AnkitJohari01`
2. Password: Use your **Personal Access Token** (NOT your GitHub password)

### To Create a Token:
1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Name: "DataPilot Local"
4. Check: ☑️ **repo** (full control)
5. Generate and copy the token
6. Use this token as your password when git asks

---

## Alternative: Single Command After Setup

If you've already pulled once, you can use this simpler version:

```bash
cd C:\Users\Ankit_Johari\Downloads\GOD_POC\DataPilot
git add .
git commit -m "Add backend and frontend code"
git push origin main
```

---

## What Will Be Pushed

✅ **Included:**
- backend/ folder (your FastAPI code)
- frontend/ folder (your React/UI code)
- requirements.txt
- .gitignore
- GITHUB_SETUP_GUIDE.md

❌ **Excluded (by .gitignore):**
- .env (environment variables - stays secret!)
- denv/ (virtual environment)
- __pycache__/ (Python cache)
- node_modules/ (if any)

---

## Verify Success

After pushing, refresh your GitHub page at:
**https://github.com/AnkitJohari01/DataPilot**

You should see all your project files!

---

**Repository URL:** https://github.com/AnkitJohari01/DataPilot  
**Created:** 2026-08-12
