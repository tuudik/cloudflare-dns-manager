# Migration from dns-records.yaml to config.yaml

If you had an existing `dns-records.yaml` file, you need to migrate to the new `config.yaml` format.

## Old Format (dns-records.yaml)

```yaml
dns_records:
  - name: frigate
    type: A
    content: 192.168.1.189
    proxied: false
    ttl: 1
```

## New Format (config.yaml)

```yaml
# Global configuration
global:
  default_ip: 192.168.1.189
  default_ttl: 1
  default_proxied: false
  docker_discovery: true
  docker_defaults:
    proxied: false
    ttl: 1
    type: A

domains:
  example.com:
    enabled: true

# Manual records (only for non-Docker services)
manual_records:
  - name: frigate
    type: A
    content: 192.168.1.189
    proxied: false
    ttl: 1
```

## Migration Steps

1. **Backup your old file** (if it exists):
   ```bash
   cd /opt/cloudflare-dns-manager
   cp dns-records.yaml dns-records.yaml.backup
   ```

2. **The new `config.yaml` already exists** with global defaults

3. **If you had manual records**, move them from `dns_records:` to `manual_records:` section in `config.yaml`

4. **Consider using Docker labels instead**:
   - For services running in Docker, use `cloudflare-dns-manager.expose=private` label
   - Only keep truly external/non-Docker services in `manual_records`

5. **Restart the service**:
   ```bash
   docker compose restart
   ```

6. **Remove old file** (optional):
   ```bash
   rm dns-records.yaml.backup
   ```

## Key Changes

✅ **Global configuration** - Set defaults once, apply everywhere
✅ **Clearer structure** - Separate manual records from auto-discovered ones  
✅ **Domain management** - Prepare for multi-domain support
✅ **Smart defaults** - Docker containers inherit global defaults, can override
✅ **Better organization** - Know what's manual vs auto-discovered

## Example: Moving Records to Docker Labels

**Before** (manual record in config):
```yaml
manual_records:
  - name: frigate
    type: A
    content: 192.168.1.189
    proxied: false
```

**After** (Docker label - recommended):
```yaml
# /opt/frigate/docker-compose.yaml
services:
  frigate:
    labels:
      - "cloudflare-dns-manager.expose=private"
      # That's it! Uses global defaults
```

Then remove from `manual_records` in config.yaml!
