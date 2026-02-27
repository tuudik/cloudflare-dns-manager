#!/usr/bin/env python3
"""
Cloudflare DNS Manager - Syncs local DNS records to Cloudflare
Watches config file and Docker containers for changes
"""

import ipaddress
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import docker
import requests
import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

LOG_LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}
INFO_CHANGE_MESSAGES = {
    "DNS record created",
    "DNS record updated",
    "DNS record deleted",
    "No DNS record changes",
}


def _get_log_level() -> str:
    value = os.getenv("CF_LOG_LEVEL", "info").strip().lower()
    if value not in LOG_LEVELS:
        return "info"
    return value


CURRENT_LOG_LEVEL = _get_log_level()


def _should_log(level: str, message: str) -> bool:
    level_name = level.strip().lower()
    if level_name not in LOG_LEVELS:
        level_name = "info"

    if LOG_LEVELS[level_name] < LOG_LEVELS[CURRENT_LOG_LEVEL]:
        return False

    if (
        CURRENT_LOG_LEVEL == "info"
        and level_name == "info"
        and message not in INFO_CHANGE_MESSAGES
    ):
        return False

    return True


def log(level: str, message: str, **kwargs):
    """Log in JSON format for Loki/Grafana"""
    if not _should_log(level, message):
        return

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "level": level.upper(),
        "message": message,
        "service": "cloudflare-dns-manager",
        **kwargs,
    }
    print(json.dumps(log_entry), flush=True)


class CloudflareDNSManager:
    MANAGED_COMMENT = os.getenv(
        "CF_MANAGED_COMMENT", "managed-by:cloudflare-dns-manager"
    )
    CONNECT_TIMEOUT = float(os.getenv("CF_CONNECT_TIMEOUT", "5"))
    READ_TIMEOUT = float(os.getenv("CF_READ_TIMEOUT", "30"))

    def __init__(self, api_token: str, zone_name: str):
        self.api_token = api_token
        self.zone_name = zone_name
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        self.zone_id = None
        self.timeout = (self.CONNECT_TIMEOUT, self.READ_TIMEOUT)

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Send a request with basic retry on rate limiting."""
        retries = 3
        backoff = 1
        response = None

        for _ in range(retries + 1):
            try:
                response = requests.request(method, url, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                log(
                    "error",
                    "Cloudflare request failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                response = requests.Response()
                response.status_code = 0
                return response
            if response.status_code != 429:
                return response

            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                time.sleep(int(retry_after))
            else:
                time.sleep(backoff)
                backoff = min(backoff * 2, 10)

        return response

    def get_zone_id(self) -> Optional[str]:
        """Get the zone ID for the domain"""
        if self.zone_id:
            return self.zone_id

        url = f"{self.base_url}/zones"
        params = {"name": self.zone_name}

        response = self._request("get", url, headers=self.headers, params=params)

        if response.status_code != 200:
            log(
                "error",
                "Failed to get zone ID",
                zone=self.zone_name,
                status=response.status_code,
            )
            return None

        data = response.json()
        if data.get("success") and data.get("result"):
            self.zone_id = data["result"][0]["id"]
            log("info", "Found zone", zone=self.zone_name, zone_id=self.zone_id)
            return self.zone_id

        log("error", "Zone not found", zone=self.zone_name)
        return None

    def get_existing_records(self) -> Dict[str, dict]:
        """Get all existing DNS records"""
        if not self.zone_id:
            return {}

        url = f"{self.base_url}/zones/{self.zone_id}/dns_records"
        params = {"per_page": 100}

        response = self._request("get", url, headers=self.headers, params=params)

        if response.status_code != 200:
            log("error", "Failed to get DNS records", status=response.status_code)
            return {}

        data = response.json()
        records = {}

        if data.get("success") and data.get("result"):
            for record in data["result"]:
                key = f"{record['name']}:{record['type']}"
                records[key] = record

        return records

    def create_record(
        self,
        name: str,
        record_type: str,
        content: str,
        proxied: bool = False,
        ttl: int = 1,
        comment: Optional[str] = None,
    ) -> bool:
        """Create a new DNS record"""
        url = f"{self.base_url}/zones/{self.zone_id}/dns_records"

        payload = {
            "type": record_type,
            "name": name,
            "content": content,
            "proxied": proxied,
            "ttl": ttl,
        }
        if comment:
            payload["comment"] = comment

        response = self._request("post", url, headers=self.headers, json=payload)

        if response.status_code == 200:
            log(
                "info",
                "DNS record created",
                name=name,
                content=content,
                type=record_type,
                proxied=proxied,
            )
            return True

        log(
            "error",
            "Failed to create DNS record",
            name=name,
            status=response.status_code,
        )
        return False

    def update_record(
        self,
        record_id: str,
        name: str,
        record_type: str,
        content: str,
        proxied: bool = False,
        ttl: int = 1,
        comment: Optional[str] = None,
    ) -> bool:
        """Update an existing DNS record"""
        url = f"{self.base_url}/zones/{self.zone_id}/dns_records/{record_id}"

        payload = {
            "type": record_type,
            "name": name,
            "content": content,
            "proxied": proxied,
            "ttl": ttl,
        }
        if comment:
            payload["comment"] = comment

        response = self._request("put", url, headers=self.headers, json=payload)

        if response.status_code == 200:
            log(
                "info",
                "DNS record updated",
                name=name,
                content=content,
                type=record_type,
                proxied=proxied,
            )
            return True

        log(
            "error",
            "Failed to update DNS record",
            name=name,
            status=response.status_code,
        )
        return False

    def delete_record(self, record_id: str, name: str) -> bool:
        """Delete a DNS record"""
        url = f"{self.base_url}/zones/{self.zone_id}/dns_records/{record_id}"

        response = self._request("delete", url, headers=self.headers)

        if response.status_code == 200:
            log("info", "DNS record deleted", name=name)
            return True

        log(
            "error",
            "Failed to delete DNS record",
            name=name,
            status=response.status_code,
        )
        return False

    def _get_full_record_name(self, name: str) -> str:
        """Return a fully-qualified record name for this zone."""
        if name.endswith(f".{self.zone_name}"):
            return name
        if name == "@":
            return self.zone_name
        return f"{name}.{self.zone_name}"

    @staticmethod
    def _record_needs_update(
        existing_record: Dict, content: str, proxied: bool, ttl: int
    ) -> bool:
        """Check whether an existing DNS record differs from desired state."""
        return (
            existing_record["content"] != content
            or existing_record["proxied"] != proxied
            or existing_record["ttl"] != ttl
        )

    def _sync_desired_record(
        self, record: Dict, existing: Dict[str, Dict]
    ) -> tuple[str, bool]:
        """Create or update a desired record and return (key, changed)."""
        name = record["name"]
        record_type = record.get("type", "A")
        content = record["content"]
        proxied = record.get("proxied", False)
        ttl = record.get("ttl", 1)

        full_name = self._get_full_record_name(name)
        key = f"{full_name}:{record_type}"

        if key not in existing:
            created = self.create_record(
                full_name,
                record_type,
                content,
                proxied,
                ttl,
                comment=self.MANAGED_COMMENT,
            )
            return key, created

        existing_record = existing[key]
        if not self._record_needs_update(existing_record, content, proxied, ttl):
            log("debug", "No change needed", name=full_name, content=content)
            return key, False

        updated = self.update_record(
            existing_record["id"],
            full_name,
            record_type,
            content,
            proxied,
            ttl,
            comment=self.MANAGED_COMMENT,
        )
        return key, updated

    def _remove_stale_managed_records(
        self, existing: Dict[str, Dict], desired_keys: set[str]
    ) -> int:
        """Delete managed records that are no longer desired."""
        removed = 0
        for key, record in existing.items():
            if key in desired_keys:
                continue
            if record.get("comment") != self.MANAGED_COMMENT:
                continue
            deleted = self.delete_record(record["id"], record["name"])
            if deleted:
                removed += 1
        return removed

    def sync_records(self, desired_records: List[Dict]) -> None:
        """Sync desired records with Cloudflare"""
        if not self.get_zone_id():
            return

        changes_made = 0

        log("info", "Fetching existing records")
        existing = self.get_existing_records()
        log("info", "Found existing records", count=len(existing))

        log("info", "Starting sync", desired_count=len(desired_records))

        desired_keys = set()

        for record in desired_records:
            key, changed = self._sync_desired_record(record, existing)
            desired_keys.add(key)
            if changed:
                changes_made += 1

        changes_made += self._remove_stale_managed_records(existing, desired_keys)

        if changes_made == 0:
            log("info", "No DNS record changes")


def load_config(config_file: str) -> tuple[Dict, List[Dict]]:
    """Load configuration and manual DNS records from config file"""
    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)

        # Extract global settings
        global_config = config.get("global", {})

        # Extract manual records
        manual_records = config.get("manual_records", [])

        log(
            "info",
            "Loaded config file",
            manual_records_count=len(manual_records),
            config_file=config_file,
            docker_discovery=global_config.get("docker_discovery", True),
        )

        return global_config, manual_records

    except Exception as e:
        log("error", "Failed to load config", error=str(e), config_file=config_file)
        return {}, []


LABEL_TOKEN = os.getenv("CF_LABEL_TOKEN")
ALLOWED_RECORD_TYPES = {"A", "AAAA", "CNAME", "TXT"}
HOST_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def _is_valid_hostname(name: str) -> bool:
    if name == "@":
        return True
    if not name or name.startswith(".") or name.endswith("."):
        return False
    labels = name.split(".")
    for label in labels:
        if label == "*":
            continue
        if not HOST_LABEL_RE.match(label):
            return False
    return True


def _normalize_record_type(record_type: str) -> str:
    return record_type.strip().upper()


def _is_truthy_label(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_public_ip() -> Optional[str]:
    """Fetch external IP used for dynamic DNS records."""
    url = "https://ipinfo.io/ip"
    try:
        response = requests.get(url, timeout=5)
    except requests.RequestException as exc:
        log(
            "error",
            "Failed to fetch external IP",
            provider="ipinfo.io",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None

    if response.status_code != 200:
        log(
            "error",
            "Failed to fetch external IP",
            provider="ipinfo.io",
            status=response.status_code,
        )
        return None

    ip = response.text.strip()
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        log(
            "error",
            "External IP provider returned invalid IP",
            provider="ipinfo.io",
            content=ip,
        )
        return None

    return ip


def _is_valid_record_content(record_type: str, content: str) -> bool:
    record_type = _normalize_record_type(record_type)
    if record_type == "A":
        try:
            return ipaddress.ip_address(content).version == 4
        except ValueError:
            return False
    if record_type == "AAAA":
        try:
            return ipaddress.ip_address(content).version == 6
        except ValueError:
            return False
    if record_type == "CNAME":
        value = content.rstrip(".")
        return _is_valid_hostname(value)
    if record_type == "TXT":
        return bool(content) and len(content) <= 255
    return False


def get_docker_records(docker_ip: str, global_config: Dict) -> List[Dict]:  # noqa: C901
    """Discover DNS records from Docker containers with cloudflare labels"""

    # Get defaults from global config
    docker_defaults = global_config.get("docker_defaults", {})
    default_ip = global_config.get("default_ip", docker_ip)
    default_proxied = docker_defaults.get("proxied", False)
    default_ttl = docker_defaults.get("ttl", 1)
    default_type = docker_defaults.get("type", "A")
    cached_public_ip: Optional[str] = None
    public_ip_attempted = False

    try:
        client = docker.from_env()
        containers = client.containers.list()
        records = []

        for container in containers:
            labels = container.labels

            # Check if container has cloudflare-dns-manager.expose label
            expose = labels.get("cloudflare-dns-manager.expose", "").lower()
            if expose not in ["true", "private", "public"]:
                continue

            is_dyndns = _is_truthy_label(
                labels.get("cloudflare-dns-manager.dyndns", "")
            )

            if LABEL_TOKEN:
                token = labels.get("cloudflare-dns-manager.token")
                if token != LABEL_TOKEN:
                    log(
                        "warning",
                        "Skipping container missing label token",
                        container=container.name,
                    )
                    continue

            # Get subdomain from label or container name
            subdomain = labels.get("cloudflare-dns-manager.subdomain")
            if not subdomain:
                # Try to get from traefik router rule
                for key, value in labels.items():
                    if (
                        "traefik.http.routers" in key
                        and ".rule=" in key
                        and "Host(" in value
                    ):
                        # Extract hostname from Host(`something.domain.xyz`)
                        import re

                        match = re.search(r"Host\(`([^`]+)`\)", value)
                        if match:
                            hostname = match.group(1)
                            # Extract subdomain (first part before domain)
                            subdomain = hostname.split(".")[0]
                            break

                # Fallback to container name
                if not subdomain:
                    subdomain = container.name

            # Get IP address (use label, then global default, then fallback)
            if is_dyndns:
                if not public_ip_attempted:
                    cached_public_ip = _get_public_ip()
                    public_ip_attempted = True
                if not cached_public_ip:
                    log(
                        "warning",
                        "Skipping dynamic DNS container due to missing external IP",
                        container=container.name,
                    )
                    continue
                ip = cached_public_ip
            else:
                ip = labels.get("cloudflare-dns-manager.ip")
                if not ip:
                    ip = default_ip

            # Get proxied setting (use label, then default)
            proxied_label = labels.get("cloudflare-dns-manager.proxied", "").lower()
            if proxied_label == "true":
                proxied = True
            elif proxied_label == "false":
                proxied = False
            else:
                proxied = default_proxied

            # Get record type (use label, then default)
            record_type = _normalize_record_type(
                labels.get("cloudflare-dns-manager.type", default_type)
            )
            if record_type not in ALLOWED_RECORD_TYPES:
                log(
                    "warning",
                    "Skipping record with invalid type",
                    container=container.name,
                    record_type=record_type,
                )
                continue

            # Get TTL (use label, then default)
            ttl_label = labels.get("cloudflare-dns-manager.ttl")
            if ttl_label:
                ttl = int(ttl_label)
            else:
                ttl = default_ttl

            if not _is_valid_hostname(subdomain):
                log(
                    "warning",
                    "Skipping record with invalid name",
                    container=container.name,
                    subdomain=subdomain,
                )
                continue

            if not _is_valid_record_content(record_type, ip):
                log(
                    "warning",
                    "Skipping record with invalid content",
                    container=container.name,
                    record_type=record_type,
                    content=ip,
                )
                continue

            record = {
                "name": subdomain,
                "type": record_type,
                "content": ip,
                "proxied": proxied,
                "ttl": ttl,
                "source": "docker",
                "container": container.name,
            }

            records.append(record)
            log(
                "info",
                "Discovered Docker service",
                container=container.name,
                subdomain=subdomain,
                ip=ip,
                expose=expose,
                dyndns=is_dyndns,
            )

        return records

    except Exception as e:
        log(
            "error",
            "Failed to discover Docker records",
            error=str(e),
            error_type=type(e).__name__,
        )
        return []


class ConfigFileHandler(FileSystemEventHandler):
    """Watches for changes to the config file"""

    def __init__(self, callback):
        self.callback = callback
        self.last_modified = 0

    def on_modified(self, event):
        if event.src_path.endswith("config.yaml"):
            # Debounce rapid file changes
            current_time = time.time()
            if current_time - self.last_modified > 1:
                self.last_modified = current_time
                log(
                    "info",
                    "Config file changed, triggering sync",
                    file=event.src_path,
                )
                self.callback()


class DNSManagerService:
    """Main service that manages DNS sync with file and Docker watching"""

    def __init__(
        self, manager: CloudflareDNSManager, config_file: str, watch_docker: bool = True
    ):
        self.manager = manager
        self.config_file = config_file
        self.watch_docker = watch_docker
        self.lock = threading.Lock()
        self.should_stop = False
        self.global_config = {}

    def sync_all(self):
        """Sync all DNS records from config file and Docker"""
        with self.lock:
            try:
                # Load config and manual records
                self.global_config, manual_records = load_config(self.config_file)

                # Check if Docker discovery is enabled
                docker_discovery_enabled = self.global_config.get(
                    "docker_discovery", True
                )

                # Load records from Docker containers
                docker_records = []
                if self.watch_docker and docker_discovery_enabled:
                    default_ip = self.global_config.get("default_ip", "192.168.1.189")
                    docker_records = get_docker_records(default_ip, self.global_config)

                # Combine all records
                all_records = manual_records + docker_records

                if not all_records:
                    log("warning", "No records found from any source")
                else:
                    log(
                        "info",
                        "Total records to sync",
                        manual_count=len(manual_records),
                        docker_count=len(docker_records),
                        total=len(all_records),
                    )
                    self.manager.sync_records(all_records)

                log("info", "Sync cycle complete")

            except Exception as e:
                log(
                    "error",
                    "Error during sync",
                    error=str(e),
                    error_type=type(e).__name__,
                )

    def watch_docker_events(self):
        """Watch Docker events for container start/stop/die"""
        try:
            client = docker.from_env()
            log("info", "Started watching Docker events")

            for event in client.events(decode=True):
                if self.should_stop:
                    break

                # React to container lifecycle events
                if event.get("Type") == "container":
                    action = event.get("Action")
                    if action in ["start", "stop", "die", "kill", "rename"]:
                        container_name = (
                            event.get("Actor", {})
                            .get("Attributes", {})
                            .get("name", "unknown")
                        )
                        log(
                            "info",
                            "Docker event detected",
                            action=action,
                            container=container_name,
                        )
                        # Trigger sync after a short delay
                        time.sleep(2)
                        self.sync_all()

        except Exception as e:
            log("error", "Docker event watcher failed", error=str(e))

    def start(self):
        """Start the DNS manager service with file and Docker watching"""
        log("info", "DNS Manager service starting")

        # Initial sync
        self.sync_all()

        # Start file watcher
        config_dir = os.path.dirname(self.config_file)
        event_handler = ConfigFileHandler(self.sync_all)
        observer = Observer()
        observer.schedule(event_handler, config_dir, recursive=False)
        observer.start()
        log("info", "Started watching config file", path=self.config_file)

        # Start Docker event watcher in separate thread
        if self.watch_docker:
            docker_thread = threading.Thread(
                target=self.watch_docker_events, daemon=True
            )
            docker_thread.start()

        try:
            # Keep running and periodically sync as backup
            while not self.should_stop:
                time.sleep(300)  # Fallback sync every 5 minutes
                log("info", "Periodic sync (backup)")
                self.sync_all()

        except KeyboardInterrupt:
            log("info", "Shutting down gracefully")
            self.should_stop = True
            observer.stop()

        observer.join()


def main():
    log("info", "Cloudflare DNS Manager starting")

    # Get configuration from environment
    api_token_file = os.getenv("CF_API_TOKEN_FILE", "/run/secrets/cf_api_token")
    zone_name = os.getenv("CF_ZONE_NAME", "example.com")
    config_file = "/app/config.yaml"
    watch_docker = os.getenv("WATCH_DOCKER", "true").lower() == "true"

    # Read API token
    try:
        with open(api_token_file, "r") as f:
            api_token = f.read().strip()
        log("info", "API token loaded", token_file=api_token_file)
    except Exception as e:
        log(
            "error", "Failed to read API token", error=str(e), token_file=api_token_file
        )
        sys.exit(1)

    # Initialize manager
    manager = CloudflareDNSManager(api_token, zone_name)

    # Start the service with file and Docker watching
    service = DNSManagerService(manager, config_file, watch_docker)
    service.start()


if __name__ == "__main__":
    main()
