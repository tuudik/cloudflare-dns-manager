# Example: Adding Cloudflare Labels to Existing Services

This file shows examples of how to add `cloudflare-dns-manager.expose` labels to your existing services.

## Frigate Example

```yaml
# /opt/frigate/docker-compose.yaml
services:
  frigate:
    container_name: frigate
    image: ghcr.io/blakeblackshear/frigate:stable
    # ... existing config ...
    labels:
      # Existing Traefik labels
      - "traefik.enable=true"
      - "traefik.http.routers.frigate.rule=Host(`frigate.example.com`)"
      - "traefik.http.routers.frigate.entrypoints=websecure"
      - "traefik.http.routers.frigate.tls.certresolver=cloudflare"
      - "traefik.http.services.frigate.loadbalancer.server.port=8971"
      
      # ADD THESE - Cloudflare auto-discovery
      - "cloudflare-dns-manager.expose=private"
      # That's it! Subdomain is auto-detected from Traefik Host rule
```

## Grafana Example

```yaml
# /opt/grafana/docker-compose.yaml
services:
  grafana:
    container_name: grafana
    image: grafana/grafana:latest
    # ... existing config ...
    labels:
      # Existing Traefik labels
      - "traefik.enable=true"
      - "traefik.http.routers.grafana.rule=Host(`grafana.example.com`)"
      - "traefik.http.routers.grafana.entrypoints=websecure"
      - "traefik.http.routers.grafana.tls.certresolver=cloudflare"
      
      # ADD THIS - Cloudflare auto-discovery
      - "cloudflare-dns-manager.expose=private"
```

## Mosquitto Example (MQTT)

```yaml
# /opt/mosquitto/docker-compose.yaml
services:
  mosquitto:
    container_name: mosquitto
    image: eclipse-mosquitto:latest
    # ... existing config ...
    labels:
      # Existing Traefik labels
      - "traefik.enable=true"
      - "traefik.http.routers.mqtt.rule=Host(`mqtt.example.com`)"
      # ... more traefik labels ...
      
      # ADD THIS - Cloudflare auto-discovery
      - "cloudflare-dns-manager.expose=private"
```

## Manual Subdomain Override

If you want a different subdomain than what Traefik has:

```yaml
labels:
  - "traefik.http.routers.myservice.rule=Host(`service.example.com`)"
  - "cloudflare-dns-manager.expose=private"
  - "cloudflare-dns-manager.subdomain=customname"  # Creates customname.example.com
```

## Custom IP Address

For services on different hosts:

```yaml
labels:
  - "cloudflare-dns-manager.expose=private"
  - "cloudflare-dns-manager.subdomain=remote-service"
  - "cloudflare-dns-manager.ip=192.168.1.100"  # Different IP
```

## After Adding Labels

1. Restart the service: `docker compose restart` (in the service directory)
2. Watch the DNS manager logs: `docker logs cloudflare-dns-manager -f`
3. You should see: "Discovered Docker service" with your container name
4. The DNS record will be created automatically in Cloudflare!

## Benefits

- ✅ Add one label, get automatic DNS management
- ✅ No manual DNS record configuration needed
- ✅ Records update when containers start/stop
- ✅ Works seamlessly with Traefik setup
- ✅ DRY principle - don't repeat hostnames
