# Telegram Bot Hosting Platform

A powerful Telegram bot that allows users to upload and run Python/JavaScript scripts in the cloud.

## Features
- Upload Python (.py) and JavaScript (.js) files
- Upload ZIP archives with dependencies
- Auto-install missing Python packages
- Run scripts in isolated environments
- Admin panel for management
- AI integration via /mpx command
- Subscription system

## Railway Deployment

### 1. Prerequisites
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Railway account (railway.app)

### 2. Deployment Steps

#### Option A: Deploy via GitHub
1. Fork this repository
2. Go to [Railway](https://railway.app)
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your repository
5. Set environment variables (see below)
6. Click "Deploy"

#### Option B: Deploy via CLI
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login to Railway
railway login

# Create new project
railway init

# Link to existing project
railway link

# Deploy
railway up
