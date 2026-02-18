# GitHub Actions Setup Guide

This document explains how to configure GitHub secrets and Cloudflare API tokens for secure CI/CD testing.

## GitHub Secrets Configuration

Go to your GitHub repository → Settings → Secrets and variables → Actions

### Required Secrets

#### 1. **CLOUDFLARE_API_TOKEN_TEST**
- **Purpose**: API token for running automated tests in CI/CD
- **Permissions Required**: 
  - `Zone:DNS:Edit` (for the test zone only)
  - `Zone:Zone:Read` (for the test zone only)
- **Security**: See Cloudflare API Token Setup section below

#### 2. **CLOUDFLARE_ZONE_ID_TEST**
- **Purpose**: Zone ID for your test domain
- **Value**: Get from Cloudflare Dashboard → Select domain → Scroll to "Zone ID"
- **Note**: Use a separate test domain/subdomain, NOT your production zone

### Optional Secrets

#### 3. **DOCKERHUB_USERNAME** (optional)
- **Purpose**: DockerHub username for publishing images
- **When**: Only if you want to publish to DockerHub in addition to GitHub Container Registry

#### 4. **DOCKERHUB_TOKEN** (optional)
- **Purpose**: DockerHub access token
- **Create at**: https://hub.docker.com/settings/security

#### 5. **CODECOV_TOKEN** (optional)
- **Purpose**: Upload test coverage reports to Codecov
- **When**: If you want coverage tracking

## Cloudflare API Token Setup

### Production Token (for your server)

Create at: Cloudflare Dashboard → My Profile → API Tokens → Create Token

**Settings:**
- **Token Name**: `cloudflare-dns-manager-production`
- **Permissions**:
  - `Zone → DNS → Edit`
  - `Zone → Zone → Read`
- **Zone Resources**:
  - Include → Specific zone → `yourdomain.com` (your production domain)
- **IP Filtering**: (Optional) Add your server's IP address
- **TTL**: (Optional) Set expiration

### Test Token (for GitHub Actions)

⚠️ **IMPORTANT**: Use a separate domain or subdomain for testing!

**Best Practice Options:**

1. **Separate Test Domain** (Recommended)
   - Register a cheap domain like `yourname-test.com` on Cloudflare (free)
   - Use this exclusively for automated testing
   - No risk to production DNS records

2. **Test Subdomain** (Alternative)
   - Create a subdomain in your existing zone: `test.yourdomain.com`
   - Less isolation but still safe if configured correctly

**Token Settings:**
- **Token Name**: `cloudflare-dns-manager-ci-test`
- **Permissions**:
  - `Zone → DNS → Edit`
  - `Zone → Zone → Read`
- **Zone Resources**:
  - Include → Specific zone → `yourtest.com` (test domain only)
  - ⚠️ **DO NOT** grant access to production zones
- **IP Filtering**: Leave empty (GitHub Actions IPs change frequently)
- **TTL**: Set to 1 year for long-term CI/CD use

### Why a Separate Test Domain?

1. **Security**: Tests create and delete DNS records - isolates production
2. **Safety**: No risk of accidentally modifying production DNS
3. **Clean Testing**: Fresh zone state for each test run
4. **CI/CD Isolation**: GitHub Actions has no access to production credentials

## Security Considerations

### How GitHub Secrets Are Protected

✅ **Secrets are encrypted** at rest in GitHub
✅ **Not visible in logs** - GitHub redacts secret values
✅ **Not accessible to forks** - PRs from forks cannot access secrets
✅ **Scoped to repository** - Only this repo can use these secrets
✅ **Audit logging** - GitHub tracks secret access

### What Users CAN'T Access

❌ Cannot read secret values from GitHub UI
❌ Cannot print secrets in Actions logs (auto-redacted)
❌ Cannot access secrets from forked repositories
❌ Cannot use secrets in pull requests from forks

### What the Test Token CAN'T Do

❌ Cannot access production DNS zones
❌ Cannot modify account settings
❌ Cannot access billing information
❌ Cannot create/delete zones
❌ Limited to the specific test zone only

## Setting Up Your Test Environment

### Step 1: Create Test Domain/Zone

Option A - Free domain on Cloudflare:
1. Use an existing free domain (e.g., from Freenom, though availability varies)
2. Add it to Cloudflare for free DNS hosting

Option B - Subdomain:
1. Go to Cloudflare Dashboard → DNS → Add Record
2. Create an A record: `test.yourdomain.com` → `127.0.0.1`

### Step 2: Create Test API Token

1. Go to: https://dash.cloudflare.com/profile/api-tokens
2. Click "Create Token"
3. Use "Edit zone DNS" template as starting point
4. Modify to only include your test zone
5. Click "Continue to summary"
6. Click "Create Token"
7. **Copy the token** (shown only once!)

### Step 3: Get Test Zone ID

1. Go to Cloudflare Dashboard
2. Select your test domain
3. Scroll down to "API" section
4. Copy the "Zone ID"

### Step 4: Add Secrets to GitHub

1. Go to: `https://github.com/tuudik/cloudflare-dns-manager/settings/secrets/actions`
2. Click "New repository secret"
3. Add `CLOUDFLARE_API_TOKEN_TEST` with your token
4. Add `CLOUDFLARE_ZONE_ID_TEST` with your zone ID

### Step 5: Update Test Configuration

If using a custom test domain, update `.github/workflows/ci.yml`:

```yaml
run: |
  cat > config.yaml << EOF
  global:
    domain: "yourtest.com"  # Change this to your test domain
    zone_id: "${CLOUDFLARE_ZONE_ID}"
    ...
```

## Verifying the Setup

After pushing to GitHub:

1. Go to Actions tab
2. Push a commit to trigger the workflow
3. Watch the "Run Tests" job
4. Check Cloudflare DNS records are created during test
5. Verify records are cleaned up after test completes

## Troubleshooting

### Tests Skipped in CI

**Problem**: Tests don't run, showing "This check was skipped"

**Solution**: The secrets might not be set. Check:
- Secrets are named exactly: `CLOUDFLARE_API_TOKEN_TEST` and `CLOUDFLARE_ZONE_ID_TEST`
- You're not running from a forked repository
- The branch is configured correctly in workflow

### API Authentication Failed

**Problem**: `401 Unauthorized` or permission errors

**Solution**:
- Verify token has `Zone:DNS:Edit` and `Zone:Zone:Read` permissions
- Check token is scoped to the correct zone
- Confirm zone ID matches the token's zone
- Token hasn't expired

### DNS Records Not Found

**Problem**: Tests fail with "Record not found"

**Solution**:
- Wait 5-10 seconds for DNS propagation
- Verify zone is active on Cloudflare
- Check domain in config.yaml matches actual zone
- Ensure API token has access to the zone

## Cost Considerations

- **Cloudflare Free Tier**: Unlimited DNS records ✅
- **GitHub Actions**: 2,000 minutes/month free (private repos) ✅
- **GitHub Container Registry**: Free for public repos ✅
- **Test Domain**: Free DNS hosting on Cloudflare ✅

**Total Cost**: $0 for most personal projects! 🎉

## Additional Resources

- [Cloudflare API Token Documentation](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)
- [GitHub Encrypted Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [Docker Hub Access Tokens](https://docs.docker.com/docker-hub/access-tokens/)
