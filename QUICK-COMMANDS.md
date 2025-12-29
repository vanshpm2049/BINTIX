# Git Commands - Copy & Paste Ready

## Setup (First Time Only)

### 1. Create GitHub Repo
Visit: https://github.com
- Click + → New repository
- Name: bintix-waste-analytics
- Click Create

### 2. Initialize & Push

Open Terminal in your project folder:

```
git init
git add .
git commit -m "Initial commit: Add Bintix Waste Analytics"
git branch -M main
git remote add origin https://github.com/yourusername/bintix-waste-analytics.git
git push -u origin main
```

Replace 'yourusername' with your GitHub username!

## Ongoing Commands

### Check changes
```
git status
```

### Save & push changes
```
git add .
git commit -m "description of changes"
git push origin main
```

### Create feature branch
```
git checkout -b feature/feature-name
git add .
git commit -m "feat: description"
git push origin feature/feature-name
```

## Deploy to Streamlit Cloud (FREE)

1. Go to: https://share.streamlit.io
2. Click "Deploy an app"
3. Select your GitHub repo
4. Select main file: at.py
5. Click Deploy

Your app URL: https://yourusername-bintix-waste-analytics.streamlit.app

## Troubleshooting

### Permission denied?
```
ssh-keygen -t ed25519 -C "your_email@example.com"
cat ~/.ssh/id_ed25519.pub
# Copy and add to GitHub Settings → SSH Keys
```

### Not a git repository?
```
git init
git remote add origin https://github.com/yourusername/bintix-waste-analytics.git
```

### Changes not pushed?
```
git push origin main
```
