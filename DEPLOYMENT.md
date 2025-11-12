# Automatic Deployment Guide

This guide explains how to set up automatic deployment to Pterodactyl using GitHub Actions.

## Prerequisites

- Pterodactyl game server panel access
- GitHub repository access
- Admin privileges on the Pterodactyl server

## Step 1: Generate Pterodactyl API Token

1. Log in to your Pterodactyl Panel
2. Navigate to **Account Settings** → **API Credentials**
3. Click **Create New** to generate a new API token
4. Set the description to "GitHub Actions Deployment"
5. Copy the API token (you'll need this in Step 3)

## Step 2: Get Your Server UUID

1. In Pterodactyl Panel, go to your Discord Bot server
2. In the server overview, you'll see the **UUID** in the server details
3. Copy the server UUID (looks like: `550e8400-e29b-41d4-a716-446655440000`)

## Step 3: Configure GitHub Secrets

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Create three new repository secrets:

   - **PTERODACTYL_API_TOKEN**: Paste your API token from Step 1
   - **PTERODACTYL_API_URL**: Your Pterodactyl Panel URL (e.g., `https://panel.example.com`)
   - **SERVER_UUID**: Your server UUID from Step 2

## Step 4: Configure Git in Pterodactyl Server

On your Pterodactyl server, ensure:

1. The bot directory is a Git repository (`git init` if needed)
2. The remote is set correctly: `git remote add origin https://github.com/humisan/humisan-bot.git`
3. SSH key is configured (or use HTTPS with personal access token)

**Optional**: Set up a startup command to auto-pull code:
- In Pterodactyl, add to your startup script: `cd /home/container && git pull origin main`

## Step 5: Test the Deployment

1. Make a small change to your repository (e.g., edit a file)
2. Push the change to the `main` branch:
   ```bash
   git add .
   git commit -m "Test deployment"
   git push origin main
   ```

3. Go to your GitHub repository → **Actions** tab
4. Watch the deployment workflow run
5. Check your Pterodactyl server logs to verify the bot updates

## How It Works

When you push code to the `main` branch:

1. **GitHub Actions detects the push**
2. **Checkout code** - The latest code is accessed
3. **Pull on server** - Pterodactyl server pulls latest changes from GitHub
4. **Restart bot** - The Discord bot is restarted with new code
5. **Notification** - You're notified of success or failure

## Troubleshooting

### "Deployment failed" error
- Verify your API token is correct in GitHub Secrets
- Check that the API token has proper permissions
- Ensure the server UUID is correct

### API calls returning 401/403 errors
- Regenerate your API token in Pterodactyl
- Make sure the token hasn't expired
- Verify the token has the `servers:read` and `servers:write` permissions

### Server not updating code
- Ensure Git is installed on the server
- Verify the Git remote is correctly configured
- Check server permissions for Git operations

### Manual Deployment
If automatic deployment fails, you can manually:
1. SSH into your Pterodactyl server
2. Navigate to the bot directory
3. Run: `git pull origin main`
4. Restart the bot through Pterodactyl Panel

## Environment Variables

Make sure your `.env` file is in the server's home directory and contains:
```
DISCORD_TOKEN=your_token_here
```

**Note**: The `.env` file should not be in Git (it's in `.gitignore`)
