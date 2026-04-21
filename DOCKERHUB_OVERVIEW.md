# Cloudflare DNS Manager

Automatically sync DNS records to Cloudflare from Docker container labels.

Cloudflare DNS Manager watches your Docker environment, discovers services that opt in via labels, and creates or updates matching DNS records in Cloudflare.

## Why use it

- Auto-discover services from Docker labels
- Create and update DNS records automatically
- Watch Docker events and config changes in real time
- Support manual records for non-Docker devices
- Structured JSON logs for observability stacks
- Multi-arch image support

## Quick start

1. Create a config file named config.yaml.
2. Run the container with your config and Docker socket mounted.
3. Add labels to your services to expose them for DNS automation.

Minimal config.yaml example:

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

Example docker-compose service:

```yaml
services:
  cloudflare-dns-manager:
    image: tuudik/cloudflare-dns-manager:latest
    container_name: cloudflare-dns-manager
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - CF_ZONE_NAME=example.com
      - WATCH_DOCKER=true
      - CF_LOG_LEVEL=info
    network_mode: host
```

## Service label example

Add labels to any service you want managed:

```yaml
services:
  whoami:
    image: traefik/whoami
    labels:
      - "cloudflare-dns-manager.expose=private"
      - "cloudflare-dns-manager.subdomain=whoami"
      - "cloudflare-dns-manager.ip=192.168.1.100"
      - "cloudflare-dns-manager.type=A"
      - "cloudflare-dns-manager.ttl=1"
```

Supported label keys:

- cloudflare-dns-manager.expose
- cloudflare-dns-manager.dyndns
- cloudflare-dns-manager.subdomain
- cloudflare-dns-manager.ip
- cloudflare-dns-manager.proxied
- cloudflare-dns-manager.type
- cloudflare-dns-manager.ttl

## Image tags

- latest: latest stable release
- vX.Y.Z: semantic version release tags

## Supported architectures

- linux/amd64
- linux/arm64
- linux/arm/v7

## Security notes

- Use a least-privilege Cloudflare API token.
- Prefer mounting a token file instead of hardcoding secrets in compose files.
- Keep config.yaml and secret files out of source control.

## Source and documentation

- GitHub repository: [https://github.com/tuudik/cloudflare-dns-manager](https://github.com/tuudik/cloudflare-dns-manager)
- Full docs and examples: README.md, EXAMPLES.md, config.yaml.example
