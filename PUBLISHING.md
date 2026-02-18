# Publishing to GitHub - Step by Step Guide

This guide walks you through publishing this project to GitHub and setting up CI/CD.

## Prerequisites

- GitHub account
- Git installed locally
- Docker Hub account (optional, for Docker Hub publishing)
- Cloudflare account with a test domain for CI/CD

## Step 1: Prepare Repository Locally

### 1.1 Initialize Git Repository

```bash
cd /opt/cloudflare-dns-manager
git init
git add .
git commit -m "Initial commit: Cloudflare DNS Manager with Docker label auto-discovery"
```

### 1.2 Verify No Credentials Are Included

Check that `.gitignore` is working:

```bash
git status
```

**Ensure these are NOT staged:**
- `config.yaml` ✓ (ignored by .gitignore)
- Any `*.secret` or `*.token` files ✓

If you see config.yaml in the list, run:
```bash
git rm --cached config.yaml
```

## Step 2: Create GitHub Repository

### 2.1 Create New Repository

1. Go to https://github.com/new
2. **Repository name**: `cloudflare-dns-manager`
3. **Description**: "Automated Cloudflare DNS manager with Docker label discovery"
4. **Visibility**: Public (for free GitHub Actions and Container Registry)
5. **DO NOT** initialize with README (we already have one)
6. Click "Create repository"

### 2.2 Push to GitHub

```bash
cd /opt/cloudflare-dns-manager

# Add remote
git remote add origin https://github.com/tuudik/cloudflare-dns-manager.git

# Push code
git branch -M main
git push -u origin main
```

## Step 3: Set Up GitHub Secrets

### 3.1 Create Test Domain

**Option A - Separate Test Domain (Recommended):**
- Use a cheap/free domain exclusively for testing
- Examples: yourname-test.com, test-domain.net
- Add to Cloudflare for free DNS

**Option B - Test Subdomain:**
- Use existing domain: test.yourdomain.com
- Less isolation but still safe

### 3.2 Create Cloudflare API Token for Testing

1. Go to: https://dash.cloudflare.com/profile/api-tokens
2. Click "Create Token"
3. **Template**: "Edit zone DNS"
4. **Permissions**:
   - Zone → DNS → Edit
   - Zone → Zone → Read
5. **Zone Resources**:
   - Include → Specific zone → `yourtest.com` (TEST DOMAIN ONLY!)
6. **IP Filtering**: Leave empty (GitHub Actions IPs change)
7. Click "Continue to summary" → "Create Token"
8. **COPY THE TOKEN** (shown only once!)

### 3.3 Get Test Zone ID

1. Cloudflare Dashboard → Select test domain
2. Scroll to "API" section
3. Copy "Zone ID"

### 3.4 Add Secrets to GitHub Repository

1. Go to: `https://github.com/tuudik/cloudflare-dns-manager/settings/secrets/actions`
2. Click "New repository secret"

**Add these secrets:**

| Secret Name | Value | Required |
|-------------|-------|----------|
| `CLOUDFLARE_API_TOKEN_TEST` | Your test API token | ✅ Yes |
| `CLOUDFLARE_ZONE_ID_TEST` | Your test zone ID | ✅ Yes |
| `DOCKERHUB_USERNAME` | Docker Hub username | ⚠️ Optional |
| `DOCKERHUB_TOKEN` | Docker Hub token | ⚠️ Optional |
| `CODECOV_TOKEN` | Codecov token | ⚠️ Optional |

**Note**: Docker images will be published to GitHub Container Registry (ghcr.io) by default. Docker Hub credentials are only needed if you also want to publish there.

### 3.5 Update CI Configuration for Test Domain

Edit `.github/workflows/ci.yml` line ~40:

```yaml
run: |
  cat > config.yaml << EOF
  global:
    domain: "yourtest.com"  # ← Change to your test domain
    zone_id: "${CLOUDFLARE_ZONE_ID}"
    ...
```

Commit and push:
```bash
git add .github/workflows/ci.yml
git commit -m "Configure test domain for CI"
git push
```

## Step 4: Verify CI/CD Pipelines

### 4.1 Check Actions

1. Go to: `https://github.com/tuudik/cloudflare-dns-manager/actions`
2. You should see two workflows running:
   - ✅ CI (testing, linting)
   - ✅ Docker Image (building multi-arch images)

### 4.2 Monitor First Build

Click on the running workflow to see logs:
- **Lint Code**: Should pass (checks Python syntax)
- **Test Docker Build**: Should pass (builds image)
- **Run Tests**: Will run if secrets are configured
- **Build and Push**: Publishes to ghcr.io

### 4.3 Verify Docker Image Published

After successful build:

1. Go to: `https://github.com/tuudik/cloudflare-dns-manager/pkgs/container/cloudflare-dns-manager`
2. You should see your image with tags:
   - `latest`
   - `main`
   - `main-<commit-sha>`

## Step 5: Test the Published Image

Pull and test your published image:

```bash
# Pull from GitHub Container Registry
docker pull ghcr.io/tuudik/cloudflare-dns-manager:latest

# Test it works
docker run --rm ghcr.io/tuudik/cloudflare-dns-manager:latest python --version
```

## Step 6: Update Production Deployment

Update your local deployment to use the published image:

```bash
cd /opt/cloudflare-dns-manager

# Backup current config
cp config.yaml config.yaml.backup

# Pull new image
docker compose pull

# Recreate container with new image
docker compose up -d

# Check logs
docker logs cloudflare-dns-manager -f
```

## Step 7: Create a Release (Optional)

### 7.1 Tag a Version

```bash
cd /opt/cloudflare-dns-manager

# Create annotated tag
git tag -a v1.0.0 -m "Release v1.0.0: Initial public release"

# Push tag
git push origin v1.0.0
```

### 7.2 Create GitHub Release

1. Go to: `https://github.com/tuudik/cloudflare-dns-manager/releases/new`
2. **Choose tag**: v1.0.0
3. **Release title**: v1.0.0 - Initial Release
4. **Description**:
```markdown
## Features
- 🐳 Docker label auto-discovery
- ⚡ Real-time config and Docker event watching
- 📊 JSON logging for Loki/Grafana
- 🚀 Multi-architecture Docker images

## Installation
\`\`\`bash
docker pull ghcr.io/tuudik/cloudflare-dns-manager:v1.0.0
\`\`\`

See [README.md](README.md) for full documentation.
```
5. Click "Publish release"

This will:
- Trigger docker-publish workflow
- Build images with version tags: `v1.0.0`, `1.0`, `1`
- Create immutable release artifacts

## Step 8: Configure GitHub Repository Settings

### 8.1 Enable Features

Repository Settings → General:

- ✅ Issues (for bug reports)
- ✅ Discussions (for community Q&A)
- ❌ Wikis (use README instead)
- ❌ Projects (not needed for small project)

### 8.2 Set Repository Topics

Add topics for discoverability:
- `cloudflare`
- `dns`
- `docker`
- `homelab`
- `self-hosted`
- `docker-compose`
- `traefik`
- `automation`

### 8.3 Set Up Branch Protection (Optional)

Settings → Branches → Add rule:
- **Branch name**: `main`
- ✅ Require status checks (CI must pass)
- ✅ Require branches to be up to date
- Required checks: `Lint Code`, `Test Docker Build`

## Step 9: Promote Your Project

### 9.1 Add Badges to README

Already added! These will update automatically:
- ![CI Badge](https://github.com/tuudik/cloudflare-dns-manager/actions/workflows/ci.yml/badge.svg)
- ![Docker Badge](https://github.com/tuudik/cloudflare-dns-manager/actions/workflows/docker-publish.yml/badge.svg)

### 9.2 Share

Consider sharing on:
- Reddit: r/selfhosted, r/homelab
- Hacker News
- Twitter/X
- Docker Hub (if published there)

## Maintenance Workflow

### Making Changes

```bash
# Create feature branch
git checkout -b feature/new-feature

# Make changes
# ... edit files ...

# Commit
git add .
git commit -m "Add new feature"

# Push
git push origin feature/new-feature
```

Then create Pull Request on GitHub. CI will automatically:
- Run linting
- Test Docker build
- Run tests (if configured)

### Updating Production

After merging to main:

```bash
cd /opt/cloudflare-dns-manager
docker compose pull  # Get latest image
docker compose up -d  # Recreate with new image
```

## Security Best Practices

✅ **DO:**
- Keep secrets in GitHub Secrets, never commit them
- Use separate test domain for CI/CD
- Limit API token permissions to specific zones
- Review pull requests before merging
- Keep dependencies updated

❌ **DON'T:**
- Commit config.yaml with real credentials
- Use production API tokens for testing
- Grant CI token access to production zones
- Merge unreviewed code to main

## Troubleshooting

### CI Tests Failing

1. Check GitHub Actions logs
2. Verify secrets are set correctly
3. Ensure test domain is accessible
4. Check API token permissions

### Docker Build Failing

1. Check Dockerfile syntax
2. Verify all required files exist
3. Check requirements.txt dependencies
4. Review build logs in Actions

### Image Not Publishing

1. Verify GITHUB_TOKEN permissions (automatic)
2. Check if running on main branch (tags/PRs)
3. Review docker-publish.yml workflow
4. Check Package settings (must be public)

## Next Steps

After successful publishing:

1. ⭐ Star your own repo (for visibility)
2. 📝 Update README with usage examples
3. 🐛 Monitor Issues for bug reports
4. 🔄 Set up Dependabot for dependency updates
5. 📊 Consider adding test coverage reporting
6. 🤝 Welcome community contributions

---

**Congratulations! Your project is now live on GitHub with full CI/CD! 🎉**
