# Deployment Instructions for Fly.io

## Initial Setup

1. **Create a Fly.io account** at https://fly.io if you haven't already

2. **Install flyctl** (if not already installed):
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

3. **Login to Fly.io**:
   ```bash
   fly auth login
   ```

4. **Launch your app** (one-time setup):
   ```bash
   fly launch --no-deploy
   ```
   - Choose a unique app name or let Fly generate one
   - Select a region close to you
   - Don't create a PostgreSQL database yet (unless you want to)
   - Don't deploy yet

## Setting up GitHub Deployment

1. **Get your Fly.io API token**:
   ```bash
   fly auth token
   ```

2. **Add the token to GitHub**:
   - Go to your GitHub repository
   - Navigate to Settings > Secrets and variables > Actions
   - Click "New repository secret"
   - Name: `FLY_API_TOKEN`
   - Value: Paste the token from step 1

3. **Set your Django secret key**:
   ```bash
   fly secrets set SECRET_KEY="$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
   ```

## Deploying

### Automatic Deployment (Recommended)
Simply push to your main/master branch:
```bash
git add .
git commit -m "Add Fly.io deployment configuration"
git push origin main
```

GitHub Actions will automatically deploy your app to Fly.io!

### Manual Deployment
If you prefer to deploy manually:
```bash
fly deploy
```

## Post-Deployment Setup

1. **Create a superuser**:
   ```bash
   fly ssh console -C "python manage.py createsuperuser"
   ```

2. **Load synonym mappings** (if you have the synonym files):
   ```bash
   fly ssh console -C "python manage.py load_synonyms --synonyms-path='../synonyms.txt' --status-synonyms-path='../status_synonyms.txt'"
   ```

## Optional: Add PostgreSQL

To use PostgreSQL instead of SQLite:

1. **Create a PostgreSQL database**:
   ```bash
   fly postgres create
   ```

2. **Attach it to your app**:
   ```bash
   fly postgres attach <postgres-app-name>
   ```

The DATABASE_URL will be automatically set, and your app will use PostgreSQL.

## Monitoring

- View logs: `fly logs`
- Open your app: `fly open`
- SSH into container: `fly ssh console`
- Check app status: `fly status`

## Troubleshooting

If deployment fails:
1. Check logs: `fly logs`
2. Ensure all migrations work: `fly ssh console -C "python manage.py migrate"`
3. Verify static files: `fly ssh console -C "python manage.py collectstatic --noinput"`