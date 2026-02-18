# Cloudflare DNS Manager

[![CI](https://github.com/tuudik/cloudflare-dns-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/tuudik/cloudflare-dns-manager/actions/workflows/ci.yml)
[![Docker Image](https://github.com/tuudik/cloudflare-dns-manager/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/tuudik/cloudflare-dns-manager/actions/workflows/docker-publish.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Automatically sync your local network DNS records to Cloudflare based on Docker container labels - like Traefik, but for DNS!

## Features

- 🐳 **Auto-discover services from Docker labels** (Traefik-style)
- ⚡ **Instant updates** - watches config file and Docker events in real-time
- ⚙️ **Global configuration** - Set defaults once in `config.yaml`
- 🔄 Creates missing records, updates changed records automatically
- 📊 **JSON logging** for Loki/Grafana integration
- 🔒 Secure API token management
- 🚀 Pre-built Docker images for easy deployment

## Quick Start

### 1. Create configuration file

Create `config.yaml` (see [config.yaml.example](config.yaml.example)):

```yaml
global:
  domain: "example.com"
  zone_id: "your_cloudflare_zone_id"
  api_token: "your_cloudflare_api_token"
  default_ip: "192.168.1.100"
  docker_discovery: true
  docker_defaults:
    proxied: false
    ttl: 1
    type: "A"

domains:
  example.com:
    zone_id: "your_cloudflare_zone_id"
    api_token: "your_cloudflare_api_token"

manual_records: []
```

### 2. Run with Docker Compose

Create `docker-compose.yml`:

```yaml
services:
  cloudflare-dns-manager:
    image: ghcr.io/tuudik/cloudflare-dns-manager:latest
    container_name: cloudflare-dns-manager
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - CF_ZONE_NAME=example.com
      - WATCH_DOCKER=true
    network_mode: host
```

### 3. Start the service

```bash
docker compose up -d
```

That's it! Now add labels to your services to create DNS records automatically.

## Docker Label Auto-Discovery

Add labels to your Docker Compose services to automatically create DNS records:

```yaml
services:
  myservice:
    image: myapp:latest
    labels:
      - "cloudflare-dns-manager.expose=private"  # Enable DNS record creation
      - "cloudflare-dns-manager.subdomain=myservice"  # Optional: defaults to container name
      - "cloudflare-dns-manager.ip=192.168.1.189"  # Optional: defaults to DOCKER_DEFAULT_IP
      - "cloudflare-dns-manager.proxied=false"  # Optional: default false
      - "cloudflare-dns-manager.type=A"  # Optional: default A
      - "cloudflare-dns-manager.ttl=1"  # Optional: default 1 (auto)
```

### Label Options:

- **`cloudflare-dns-manager.expose`**: Required. Set to `true`, `private`, or `public` to enable
- **`cloudflare-dns-manager.subdomain`**: Subdomain name (auto-detected from Traefik labels or container name)
- **`cloudflare-dns-manager.ip`**: IP address (defaults to `global.default_ip` from config.yaml)
- **`cloudflare-dns-manager.proxied`**: Whether to proxy through Cloudflare (defaults to `global.default_proxied`)
- **`cloudflare-dns-manager.type`**: Record type (defaults to `global.docker_defaults.type`)
- **`cloudflare-dns-manager.ttl`**: TTL in seconds (defaults to `global.docker_defaults.ttl`)

### Example with Traefik:

```yaml
services:
  whoami:
    image: traefik/whoami
    labels:
      # Traefik labels
      - "traefik.enable=true"
      - "traefik.http.routers.whoami.rule=Host(`whoami.example.com`)"
      - "traefik.http.routers.whoami.entrypoints=websecure"
      
      # Cloudflare auto-discovery (subdomain auto-detected from Traefik!)
      - "cloudflare-dns-manager.expose=private"
```

The DNS manager will automatically:
1. Detect the `whoami` service has `cloudflare-dns-manager.expose=private`
2. Extract `whoami` subdomain from Traefik's Host rule
3. Create DNS record: `whoami.example.com` → `192.168.1.100`

## Getting Your Cloudflare API Token

### Step 1: Create API Token

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/profile/api-tokens)
2. Click "Create Token"
3. Use "Edit zone DNS" template
4. **Permissions**:
   - `Zone → DNS → Edit`
   - `Zone → Zone → Read`
5. **Zone Resources**:
   - Include → Specific zone → `yourdomain.com`
6. Create Token and copy it (shown only once!)

### Step 2: Get Zone ID

1. Go to Cloudflare Dashboard
2. Select your domain
3. Scroll down to "API" section
4. Copy the "Zone ID"

See [GITHUB_SETUP.md](GITHUB_SETUP.md) for more details on API token security.

## Usage

### Check logs:
```bash
docker logs cloudflare-dns-manager -f
```

All logs are in **JSON format** for easy parsing by Loki/Promtail:
```json
{"timestamp": "2026-02-18T12:34:56Z", "level": "INFO", "message": "DNS record created", "name": "myservice.example.com", "content": "192.168.1.100", "service": "cloudflare-dns-manager"}
```

### Manual restart (if needed):
```bash
docker compose restart cloudflare-dns-manager
```
**Note**: Restart is rarely needed - config file changes and Docker events are detected automatically!

## How It Works

1. **Config Loading**: Reads global settings from `config.yaml`
2. **File Watching**: Detects changes to `config.yaml` instantly (like Traefik dynamic config)
3. **Docker Watching**: Monitors Docker events (container start/stop) for auto-discovery
4. **Auto-Discovery**: Reads Docker labels to automatically create DNS records
5. Compares with existing Cloudflare DNS records
6. Creates new records that don't exist
7. Updates records that have changed
8. Leaves other records untouched

## Adding New Records

### Method 1: Docker Labels (Recommended)
1. Add `cloudflare-dns-manager.expose=private` label to your service
2. Start/restart the container
3. **DNS record is created automatically!**
4. Check logs to verify: `docker logs cloudflare-dns-manager -f`

### Method 2: Manual Config (For non-Docker services)
1. Edit `config.yaml` and add to `manual_records:` section
2. **Changes are detected automatically!** No restart needed.
3. Check logs to verify: `docker logs cloudflare-dns-manager -f`

**Example manual record in config.yaml:**
```yaml
manual_records:
  - name: printer
    type: A
    content: 192.168.1.50
    proxied: false
    ttl: 1
```

## Example Manual Records

For non-Docker services or external devices only:

```yaml
manual_records:
  # External devices NOT running in Docker
  - name: nas
    type: A
    content: 192.168.1.100
    proxied: false
  
  - name: printer
    type: A
    content: 192.168.1.50
    proxied: false
  
  - name: router
    type: A
    content: 192.168.1.1
    proxied: false
  
  # CNAME example
  - name: www
    type: CNAME
    content: example.com
    proxied: false
```

**Note**: Docker services (frigate, mqtt, grafana, etc.) should use Docker labels instead!

## Important Notes

- Changes to `config.yaml` are detected **instantly** (no restart needed!)
- Container start/stop events trigger **automatic** DNS updates
- **Prefer Docker labels over manual records** for services running in Docker
- Manual records in `config.yaml` are for non-Docker services only
- The service only manages records defined in config or Docker labels
- Other records in your Cloudflare zone are left untouched
- See [EXAMPLES.md](EXAMPLES.md) for adding labels to existing services

## Troubleshooting

### View current status:
```bash
docker logs cloudflare-dns-manager --tail 50
```

### Force immediate sync:
```bash
docker compose restart cloudflare-dns-manager
```

### Verify DNS records in Cloudflare:
Visit: https://dash.cloudflare.com/ → Select your domain → DNS

### Common Issues

**Records not being created:**
- Check logs for errors: `docker logs cloudflare-dns-manager`
- Verify API token has correct permissions
- Ensure zone ID matches your domain
- Confirm Docker socket is mounted correctly

**Container not starting:**
- Check config.yaml syntax (valid YAML)
- Ensure config.yaml exists and is readable
- Verify Docker socket permissions

## Installation Options

### Option 1: Pre-built Image (Recommended)

```bash
docker pull ghcr.io/tuudik/cloudflare-dns-manager:latest
```

### Option 2: Build from Source

```bash
git clone https://github.com/tuudik/cloudflare-dns-manager.git
cd cloudflare-dns-manager
docker build -t cloudflare-dns-manager .
```

### Option 3: Docker Compose Development

```bash
git clone https://github.com/tuudik/cloudflare-dns-manager.git
cd cloudflare-dns-manager
cp config.yaml.example config.yaml
# Edit config.yaml with your values
docker compose up -d
```

## Available Docker Images

- `ghcr.io/tuudik/cloudflare-dns-manager:latest` - Latest stable release
- `ghcr.io/tuudik/cloudflare-dns-manager:main` - Latest from main branch
- `ghcr.io/tuudik/cloudflare-dns-manager:vX.Y.Z` - Specific version tags

Supported architectures: `linux/amd64`, `linux/arm64`, `linux/arm/v7`

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `./run_tests.sh`
5. Submit a pull request

See [GITHUB_SETUP.md](GITHUB_SETUP.md) for CI/CD details.

## Testing

Run the test suite:

```bash
./run_tests.sh
```

This will:
- Start test containers with various label configurations
- Verify DNS records are created correctly
- Test auto-discovery and config parsing

## Related Projects

- [cloudflare-ddns](https://github.com/oznu/docker-cloudflare-ddns) - For updating external IP addresses
- [Traefik](https://traefik.io/) - Works great with this for reverse proxy + DNS automation

## License

MIT License - see [LICENSE](LICENSE) file for details

## Support

- 📝 [Documentation](https://github.com/tuudik/cloudflare-dns-manager)
- 🐛 [Issues](https://github.com/tuudik/cloudflare-dns-manager/issues)
- 💬 [Discussions](https://github.com/tuudik/cloudflare-dns-manager/discussions)

---

Made with ❤️ for homelabs everywhere
