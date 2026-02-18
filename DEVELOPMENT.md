# Development and Deployment Structure

This project uses a separated structure for development/GitHub and production deployment.

## Directory Structure

### `/home/tuudik/cloudflare-dns-manager/` (This Directory)
**GitHub Repository** - Public source code and documentation

Contains:
- Source code (`dns-manager.py`)
- Dockerfile and build configuration
- Documentation (README.md, EXAMPLES.md, etc.)
- CI/CD workflows (`.github/workflows/`)
- Test suite (`test_dns_manager.py`, `run_tests.sh`)
- Template files (`config.yaml.example`, `docker-compose.override.yml.example`)

**This is what gets published to GitHub and Docker Hub.**

### `/opt/cloudflare-dns-manager/`
**Production Deployment** - Your actual running instance

Contains:
- `config.yaml` - Your real Cloudflare credentials (NEVER commit to git!)
- `docker-compose.local.yaml` - Local deployment configuration
- Uses pre-built image: `ghcr.io/tuudik/cloudflare-dns-manager:latest`

**This contains your production credentials and stays local.**

## Development Workflow

### 1. Make Changes (in this directory)
```bash
cd /home/tuudik/cloudflare-dns-manager
# Edit dns-manager.py or other files
```

### 2. Test Locally
```bash
# Build and test
docker build -t cloudflare-dns-manager:dev .

# Or run tests
./run_tests.sh
```

### 3. Commit and Push
```bash
git add .
git commit -m "Your changes"
git push origin main
```

### 4. GitHub Actions Will:
- Run linting and tests
- Build multi-architecture Docker images
- Publish to `ghcr.io/tuudik/cloudflare-dns-manager:latest`

### 5. Update Production
```bash
cd /opt/cloudflare-dns-manager
docker compose -f docker-compose.local.yaml pull
docker compose -f docker-compose.local.yaml up -d
```

## Security

✅ **Protected by .gitignore:**
- `config.yaml` - Real credentials
- `docker-compose.override.yml` - Local customization
- `docker-compose.local.yaml` - Production deployment
- `*.secret`, `*.token` - Any secrets

❌ **Never in Git:**
- Your personal domain in code - use example.com in templates
- Cloudflare API tokens
- Production paths or credentials

## Quick Reference

### Development Commands
```bash
cd /home/tuudik/cloudflare-dns-manager

# Run tests
./run_tests.sh

# Build image
docker build -t cloudflare-dns-manager:test .

# Format code
black dns-manager.py

# Lint code
flake8 dns-manager.py
```

### Production Commands
```bash
cd /opt/cloudflare-dns-manager

# Start service
docker compose -f docker-compose.local.yaml up -d

# View logs
docker logs cloudflare-dns-manager -f

# Update to latest
docker compose -f docker-compose.local.yaml pull
docker compose -f docker-compose.local.yaml up -d

# Restart
docker compose -f docker-compose.local.yaml restart
```

## Files Overview

### GitHub Repository Files (Public)
- `dns-manager.py` - Main application
- `Dockerfile` - Container build
- `requirements.txt` - Python dependencies
- `docker-compose.yaml` - Generic template
- `config.yaml.example` - Configuration template
- `.gitignore` - Excludes credentials and local files
- `.dockerignore` - Excludes files from Docker build
- `README.md` - Public documentation
- `LICENSE` - MIT license
- CI/CD workflows, tests, examples

### Local Deployment Files (Private)
- `config.yaml` - Real credentials
- `docker-compose.local.yaml` - Production compose file
- `README.local.md` - Local deployment notes

## Initial Setup (Already Done)

This structure was created with:
```bash
# Created GitHub repository
mkdir -p /home/tuudik/cloudflare-dns-manager

# Copied public files from /opt
cp [public files] /home/tuudik/cloudflare-dns-manager/

# Cleaned /opt to only deployment files
rm [development files from /opt]

# Updated .gitignore to exclude local deployment files
```

## Benefits

1. ✅ **Clean Separation** - Development code separate from production config
2. ✅ **Security** - Credentials never accidentally committed
3. ✅ **Easy Updates** - Pull pre-built images in production
4. ✅ **Version Control** - Track code changes without config changes
5. ✅ **Public Sharing** - Share code without exposing your setup
