# Pre-Publishing Checklist

This checklist ensures no credentials are committed to GitHub.

## ✅ Files Sanitized for Public GitHub

- [x] `.gitignore` - Excludes config.yaml, *.token, secrets/, docker-compose.override.yml
- [x] `docker-compose.yaml` - Generic template using example.com
- [x] `config.yaml.example` - Example configuration without real credentials
- [x] `docker-compose.override.yml.example` - Shows how to customize locally
- [x] `dns-manager.py` - Default domain changed to example.com
- [x] `test_dns_manager.py` - Default domain changed to example.com
- [x] `run_tests.sh` - Uses example.com
- [x] `README.md` - All examples use example.com
- [x] `EXAMPLES.md` - All examples use example.com
- [x] `MIGRATION.md` - All examples use example.com
- [x] `GITHUB_SETUP.md` - Security documentation
- [x] `PUBLISHING.md` - Step-by-step publishing guide

## 🔒 Files That Stay Local (git ignored)

These files contain your actual credentials and domain:

- `config.yaml` - Your real Cloudflare credentials
- `docker-compose.override.yml` - Your local customization with your domain
- `*.token` - Any token files
- `secrets/` - Any secret directories

## ⚠️ Verify Before Push

Run these commands before pushing to GitHub:

```bash
# Check what will be committed
git status

# Verify config.yaml is NOT staged
git status | grep -q "config.yaml" && echo "❌ WARNING: config.yaml will be committed!" || echo "✅ config.yaml is ignored"

# Verify override is NOT staged
git status | grep -q "docker-compose.override.yml" && echo "❌ WARNING: override will be committed!" || echo "✅ override is ignored"

# Search for your domain in staged files (replace with your actual domain)
git diff --cached | grep -i "yourdomain.com" && echo "❌ WARNING: Found your domain in staged changes!" || echo "✅ No personal domain found"

# Check for API tokens
git diff --cached | grep -i "token" && echo "⚠️ Review: Token references found (verify they are examples only)"
```

## 📦 What Will Be Published

Public Docker images will contain:
- ✅ Python application code (dns-manager.py)
- ✅ Required dependencies (requirements.txt)
- ❌ NO configuration files
- ❌ NO credentials
- ❌ NO personal data

Users will provide their own:
- config.yaml (from config.yaml.example)
- docker-compose.override.yml (from example)
- Cloudflare API tokens

## 🔐 GitHub Secrets Setup

For CI/CD testing, you'll need to create GitHub Secrets:

**Required Secrets:**
- `CLOUDFLARE_API_TOKEN_TEST` - API token for TEST domain only
- `CLOUDFLARE_ZONE_ID_TEST` - Zone ID for TEST domain

**Important:** 
- ⚠️ Use a SEPARATE test domain (not your production domain)
- ⚠️ Test token should ONLY have access to test domain
- ⚠️ Never use production credentials in GitHub Secrets

See [GITHUB_SETUP.md](GITHUB_SETUP.md) for detailed instructions.

## 🚀 Ready to Publish?

If all checks pass, follow: [PUBLISHING.md](PUBLISHING.md)

### Quick Publishing Commands

```bash
cd /opt/cloudflare-dns-manager

# Initialize git
git init
git add .
git commit -m "Initial commit: Cloudflare DNS Manager"

# Verify no credentials
git log --stat | grep -i config.yaml && echo "❌ STOP!" || echo "✅ Safe to push"

# Add remote and push
git remote add origin https://github.com/tuudik/cloudflare-dns-manager.git
git branch -M main
git push -u origin main
```

## Local Development After Publishing

Your local setup remains unchanged:
- `config.yaml` stays with your real credentials
- `docker-compose.override.yml` stays with your domain
- Test containers keep working with your domain

When you pull from GitHub:
```bash
git pull origin main
# Your local config.yaml and override files are NOT affected (ignored by git)
```

## Testing After Sanitization

Verify the public version works:

```bash
# Create a test directory
mkdir /tmp/cloudflare-dns-test
cd /tmp/cloudflare-dns-test

# Copy public files only
cp /opt/cloudflare-dns-manager/docker-compose.yaml .
cp /opt/cloudflare-dns-manager/config.yaml.example config.yaml
cp /opt/cloudflare-dns-manager/Dockerfile .

# Verify no credentials
grep -r "yourdomain.com" . && echo "❌ Found personal domain!" || echo "✅ Clean"
grep -r "your_actual_token" . && echo "❌ Found real token!" || echo "✅ Clean"

# Cleanup
cd /opt/cloudflare-dns-manager
rm -rf /tmp/cloudflare-dns-test
```
