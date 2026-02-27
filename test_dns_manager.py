#!/usr/bin/env python3
"""
Test suite for Cloudflare DNS Manager
"""

import importlib.util
import os
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, List, Tuple

import docker
import pytest
import requests

# Configuration
CF_API_TOKEN_FILE = os.getenv("CF_API_TOKEN_FILE", "/run/secrets/cf_api_token")
CF_ZONE_NAME = os.getenv("CF_ZONE_NAME", "example.com")
CF_ZONE_ID = os.getenv("CF_ZONE_ID")
TEST_SLEEP = 10  # Seconds to wait for DNS sync (increased for API propagation)
REQUIRE_CF_TESTS = os.getenv("REQUIRE_CF_TESTS", "").lower() in ("1", "true", "yes")
DNS_MANAGER_PATH = Path(__file__).with_name("dns-manager.py")
REDACT_TOKEN = "<redacted-domain>"


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"


class DummyResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class DummyContainer:
    def __init__(self, name: str, labels: dict):
        self.name = name
        self.labels = labels


class DummyClient:
    def __init__(self, containers):
        self._containers = containers
        self.containers = self

    def list(self):
        return self._containers


def log_test(name: str, status: str, message: str = ""):
    """Pretty print test results"""
    if CF_ZONE_NAME:
        message = message.replace(CF_ZONE_NAME, REDACT_TOKEN)
    if status == "PASS":
        symbol = f"{Colors.GREEN}✓{Colors.RESET}"
    elif status == "FAIL":
        symbol = f"{Colors.RED}✗{Colors.RESET}"
    else:
        symbol = f"{Colors.YELLOW}•{Colors.RESET}"

    print(f"{symbol} {Colors.BLUE}{name}{Colors.RESET}: {message}")


class CloudflareAPI:
    """Simple Cloudflare API client for testing"""

    def __init__(self, api_token: str, zone_name: str):
        self.api_token = api_token
        self.zone_name = zone_name
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        self.session = requests.Session()
        self.zone_id = None

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        retries = 5
        backoff = 1
        response = None

        for _ in range(retries + 1):
            response = self.session.request(method, url, **kwargs)
            if response.status_code != 429:
                return response

            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                time.sleep(int(retry_after))
            else:
                time.sleep(backoff)
                backoff = min(backoff * 2, 10)

        return response

    def _log_api_error(self, action: str, response: requests.Response) -> None:
        log_test(
            "Cloudflare API",
            "FAIL",
            f"{action} failed ({response.status_code}): {response.text}",
        )

    def get_zone_id(self) -> str:
        """Get zone ID"""
        if self.zone_id:
            return self.zone_id

        url = f"{self.base_url}/zones"
        params = {"name": self.zone_name}
        response = self._request("get", url, headers=self.headers, params=params)

        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("result"):
                self.zone_id = data["result"][0]["id"]
                return self.zone_id
            self._log_api_error("Get zone ID", response)
            return None

        self._log_api_error("Get zone ID", response)
        return None

    def get_zone_name(self) -> str:
        """Fetch zone name when only zone ID is known."""
        if not self.zone_id:
            return None

        url = f"{self.base_url}/zones/{self.zone_id}"
        response = self._request("get", url, headers=self.headers)

        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("result"):
                self.zone_name = data["result"]["name"]
                return self.zone_name
            self._log_api_error("Get zone name", response)
            return None

        self._log_api_error("Get zone name", response)
        return None

    def get_record(self, name: str, record_type: str = "A") -> Dict:
        """Get a specific DNS record"""
        if not self.zone_id:
            self.get_zone_id()

        full_name = f"{name}.{self.zone_name}" if name != "@" else self.zone_name

        url = f"{self.base_url}/zones/{self.zone_id}/dns_records"
        params = {"name": full_name, "type": record_type}
        response = self._request("get", url, headers=self.headers, params=params)

        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("result"):
                return data["result"][0] if data["result"] else None
            if data.get("success") and not data.get("result"):
                return None
            self._log_api_error("Get record", response)
            return None

        self._log_api_error("Get record", response)
        return None

    def delete_record(self, record_id: str) -> bool:
        """Delete a DNS record"""
        if not self.zone_id:
            self.get_zone_id()

        url = f"{self.base_url}/zones/{self.zone_id}/dns_records/{record_id}"
        response = self._request("delete", url, headers=self.headers)
        return response.status_code == 200


def read_api_token() -> str:
    """Read Cloudflare API token"""
    try:
        with open(CF_API_TOKEN_FILE, "r") as f:
            return f.read().strip()
    except Exception as e:
        print(f"{Colors.RED}Failed to read API token: {e}{Colors.RESET}")
        sys.exit(1)


def generate_random_ip() -> str:
    """Generate a random documentation-range IPv4 address."""
    base = random.choice(["192.0.2", "198.51.100", "203.0.113"])
    return f"{base}.{random.randint(1, 254)}"


def setup_test_containers() -> (
    Tuple[List[dict], List[docker.models.containers.Container]]
):
    """Create temporary test containers with randomized IP labels."""
    run_id = uuid.uuid4().hex[:8]
    client = docker.from_env()
    containers = []

    test_defs = [
        {
            "base_name": "cf-test-minimal",
            "subdomain": None,
            "description": "Minimal label configuration",
        },
        {
            "base_name": "cf-test-custom-subdomain",
            "subdomain": f"testsubdomain-{run_id}",
            "description": "Custom subdomain override",
        },
        {
            "base_name": "cf-test-custom-ip",
            "subdomain": None,
            "description": "Custom IP address",
        },
        {
            "base_name": "cf-test-traefik-host",
            "subdomain": f"traefik-{run_id}",
            "description": "Container name fallback (Traefik extraction needs proper router)",
            "traefik": True,
        },
    ]

    tests = []
    for test_def in test_defs:
        container_name = f"{test_def['base_name']}-{run_id}"
        ip_address = generate_random_ip()
        labels = {
            "cloudflare-dns-manager.expose": "private",
            "cloudflare-dns-manager.ip": ip_address,
        }
        if test_def.get("subdomain"):
            labels["cloudflare-dns-manager.subdomain"] = test_def["subdomain"]
        if test_def.get("traefik"):
            labels[f"traefik.http.routers.{container_name}.rule"] = (
                f"Host(`{test_def['subdomain']}.{CF_ZONE_NAME}`)"
            )

        container = client.containers.run(
            "alpine:latest",
            "sleep infinity",
            detach=True,
            name=container_name,
            labels=labels,
        )
        containers.append(container)

        record_name = test_def.get("subdomain") or container_name
        tests.append(
            {
                "name": record_name,
                "expected_ip": ip_address,
                "description": test_def["description"],
            }
        )

    return tests, containers


def cleanup_test_containers(
    containers: List[docker.models.containers.Container],
) -> None:
    """Stop and remove temporary test containers."""
    for container in containers:
        try:
            container.remove(force=True)
            log_test(f"Container cleanup: {container.name}", "PASS", "Removed")
        except Exception as e:
            log_test(f"Container cleanup: {container.name}", "FAIL", str(e))


def load_dns_manager_module():
    """Load dns-manager.py as a module for direct invocation."""
    if not DNS_MANAGER_PATH.exists():
        pytest.fail("dns-manager.py not found")
    spec = importlib.util.spec_from_file_location("dns_manager", DNS_MANAGER_PATH)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        pytest.fail("Failed to load dns-manager module")
    spec.loader.exec_module(module)

    original_log = module.log

    def redacted_log(level: str, message: str, **kwargs):
        if CF_ZONE_NAME:
            message = message.replace(CF_ZONE_NAME, REDACT_TOKEN)
        redacted_kwargs = {}
        for key, value in kwargs.items():
            if isinstance(value, str) and CF_ZONE_NAME:
                redacted_kwargs[key] = value.replace(CF_ZONE_NAME, REDACT_TOKEN)
            else:
                redacted_kwargs[key] = value
        original_log(level, message, **redacted_kwargs)

    module.log = redacted_log
    return module


def test_dyndns_record_uses_external_ip_and_proxied_label(monkeypatch):
    module = load_dns_manager_module()

    containers = [
        DummyContainer(
            "web",
            {
                "cloudflare-dns-manager.expose": "private",
                "cloudflare-dns-manager.dyndns": "true",
                "cloudflare-dns-manager.subdomain": "home",
                "cloudflare-dns-manager.proxied": "true",
            },
        )
    ]

    monkeypatch.setattr(module.docker, "from_env", lambda: DummyClient(containers))
    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *args, **kwargs: DummyResponse(200, "203.0.113.10\n"),
    )

    records = module.get_docker_records("192.168.1.100", {"docker_defaults": {}})

    assert len(records) == 1
    assert records[0]["name"] == "home"
    assert records[0]["content"] == "203.0.113.10"
    assert records[0]["proxied"] is True


def test_dyndns_public_ip_is_fetched_once_per_discovery(monkeypatch):
    module = load_dns_manager_module()

    containers = [
        DummyContainer(
            "svc-a",
            {
                "cloudflare-dns-manager.expose": "true",
                "cloudflare-dns-manager.dyndns": "true",
            },
        ),
        DummyContainer(
            "svc-b",
            {
                "cloudflare-dns-manager.expose": "true",
                "cloudflare-dns-manager.dyndns": "true",
            },
        ),
    ]

    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        return DummyResponse(200, "198.51.100.11")

    monkeypatch.setattr(module.docker, "from_env", lambda: DummyClient(containers))
    monkeypatch.setattr(module.requests, "get", fake_get)

    records = module.get_docker_records("192.168.1.100", {"docker_defaults": {}})

    assert len(records) == 2
    assert all(record["content"] == "198.51.100.11" for record in records)
    assert calls["count"] == 1


@pytest.fixture(scope="module")
def test_env():
    """Create temporary test containers and return test records + containers."""
    try:
        client = docker.from_env()
        client.ping()
    except Exception as e:
        if REQUIRE_CF_TESTS:
            pytest.fail(f"Docker not available: {e}")
        pytest.skip(f"Docker not available: {e}")

    tests, containers = setup_test_containers()
    yield tests, containers
    cleanup_test_containers(containers)


@pytest.fixture(scope="module")
def tests(test_env) -> List[Dict]:
    return test_env[0]


@pytest.fixture(scope="module")
def containers(test_env) -> List[docker.models.containers.Container]:
    return test_env[1]


@pytest.fixture(scope="module")
def api() -> CloudflareAPI:
    try:
        api_token = read_api_token()
    except SystemExit:
        if REQUIRE_CF_TESTS:
            pytest.fail("Missing API token")
        pytest.skip("Missing API token")
    api_client = CloudflareAPI(api_token, CF_ZONE_NAME)
    if CF_ZONE_ID:
        api_client.zone_id = CF_ZONE_ID
        if api_client.zone_name:
            return api_client
        if not api_client.get_zone_name():
            if REQUIRE_CF_TESTS:
                pytest.fail("Failed to fetch zone name")
            pytest.skip("Failed to fetch zone name")
        return api_client
    if not api_client.get_zone_id():
        if REQUIRE_CF_TESTS:
            pytest.fail("Failed to get zone ID")
        pytest.skip("Failed to get zone ID")
    return api_client


@pytest.fixture(scope="module")
def dns_manager_module():
    return load_dns_manager_module()


@pytest.fixture(scope="module")
def sync_records(api: CloudflareAPI, tests: List[Dict], dns_manager_module):
    manager = dns_manager_module.CloudflareDNSManager(api.api_token, api.zone_name)
    manager.zone_id = api.zone_id
    desired_records = [
        {
            "name": test["name"],
            "type": "A",
            "content": test["expected_ip"],
            "proxied": False,
            "ttl": 1,
        }
        for test in tests
    ]
    manager.sync_records(desired_records)
    try:
        yield
    finally:
        record_names = [test["name"] for test in tests]
        cleanup_test_records(api, record_names)
        cleanup_stale_test_records(api, dns_manager_module)


def test_docker_containers(
    containers: List[docker.models.containers.Container],
) -> None:
    """Test that test containers are running"""
    log_test("Test Scope", "INFO", "Function: test_docker_containers")
    log_test("Docker Connection", "INFO", "Checking test containers...")

    running_containers = []
    for container in containers:
        container.reload()
        if container.status == "running":
            running_containers.append(container.name)
            log_test(
                f"Container: {container.name}",
                "PASS",
                f"Status: {container.status}",
            )
        else:
            log_test(
                f"Container: {container.name}",
                "FAIL",
                f"Status: {container.status}",
            )

    result = len(running_containers) == len(containers)
    assert result


def wait_for_record_content(
    api: CloudflareAPI,
    record_name: str,
    expected_ip: str,
    timeout_seconds: int = 20,
    max_interval: int = 8,
) -> Tuple[bool, Dict]:
    """Wait until a DNS record matches the expected IP using exponential backoff."""
    deadline = time.time() + timeout_seconds
    interval = 1
    last_record = None

    while time.time() < deadline:
        last_record = api.get_record(record_name)
        if last_record and last_record.get("content") == expected_ip:
            return True, last_record
        time.sleep(interval)
        interval = min(interval * 2, max_interval)

    return False, last_record


def run_dns_record_checks(
    api: CloudflareAPI,
    tests: List[Dict],
    timeout_seconds: int = 20,
    phase: str = "check",
) -> Tuple[int, int]:
    """Check that DNS records are created correctly and return counts."""
    log_test("DNS Records", "INFO", f"Phase: {phase}")
    log_test("DNS Records", "INFO", f"Waiting {TEST_SLEEP}s for sync...")
    time.sleep(TEST_SLEEP)

    passed = 0
    failed = 0

    for test in tests:
        expected_ip = test["expected_ip"]
        matched, record = wait_for_record_content(
            api,
            test["name"],
            expected_ip,
            timeout_seconds=timeout_seconds,
        )

        if matched:
            log_test(
                f"Record: {test['name']}",
                "PASS",
                f"IP: {expected_ip} - {test['description']}",
            )
            passed += 1
        else:
            if record:
                log_test(
                    f"Record: {test['name']}",
                    "FAIL",
                    f"Expected {expected_ip}, got {record.get('content')}",
                )
            else:
                log_test(
                    f"Record: {test['name']}",
                    "FAIL",
                    f"Record not found - {test['description']}",
                )
            failed += 1

    return passed, failed


def wait_for_record_absence(
    api: CloudflareAPI,
    record_name: str,
    timeout_seconds: int = 10,
    max_interval: int = 8,
) -> bool:
    """Wait until a DNS record no longer exists using exponential backoff."""
    deadline = time.time() + timeout_seconds
    interval = 1
    while time.time() < deadline:
        if api.get_record(record_name) is None:
            return True
        time.sleep(interval)
        interval = min(interval * 2, max_interval)
    return False


def update_dns_records(
    api: CloudflareAPI,
    dns_manager_module,
    tests: List[Dict],
) -> List[Dict]:
    """Update existing DNS records to new IPs and return updated expectations."""
    manager = dns_manager_module.CloudflareDNSManager(api.api_token, api.zone_name)
    manager.zone_id = api.zone_id

    updated_tests = []
    for test in tests:
        new_ip = generate_random_ip()
        while new_ip == test["expected_ip"]:
            new_ip = generate_random_ip()

        updated_tests.append(
            {
                "name": test["name"],
                "expected_ip": new_ip,
                "description": f"Update record: {test['description']}",
            }
        )

    desired_records = [
        {
            "name": test["name"],
            "type": "A",
            "content": test["expected_ip"],
            "proxied": False,
            "ttl": 1,
        }
        for test in updated_tests
    ]
    manager.sync_records(desired_records)
    return updated_tests


def create_dyndns_test_container() -> docker.models.containers.Container:
    """Create a temporary container configured for dyndns discovery."""
    run_id = uuid.uuid4().hex[:8]
    container_name = f"cf-test-dyndns-{run_id}"
    labels = {
        "cloudflare-dns-manager.expose": "private",
        "cloudflare-dns-manager.dyndns": "true",
        "cloudflare-dns-manager.subdomain": f"dyndns-{run_id}",
        "cloudflare-dns-manager.proxied": "true",
        "cloudflare-dns-manager.type": "A",
        "cloudflare-dns-manager.ttl": "1",
    }

    client = docker.from_env()
    return client.containers.run(
        "alpine:latest",
        "sleep infinity",
        detach=True,
        name=container_name,
        labels=labels,
    )


def test_dns_records(
    api: CloudflareAPI,
    tests: List[Dict],
    dns_manager_module,
    sync_records,
) -> None:
    """Test that DNS records are created correctly"""
    log_test("Test Scope", "INFO", "Function: test_dns_records (create/update/delete)")
    passed, failed = run_dns_record_checks(
        api, tests, timeout_seconds=30, phase="create"
    )
    assert failed == 0

    updated_tests = update_dns_records(api, dns_manager_module, tests)
    passed, failed = run_dns_record_checks(
        api, updated_tests, timeout_seconds=60, phase="update"
    )
    assert failed == 0

    manager = dns_manager_module.CloudflareDNSManager(api.api_token, api.zone_name)
    manager.zone_id = api.zone_id
    remaining_tests = updated_tests[:-1]
    removed_test = updated_tests[-1]
    desired_records = [
        {
            "name": test["name"],
            "type": "A",
            "content": test["expected_ip"],
            "proxied": False,
            "ttl": 1,
        }
        for test in remaining_tests
    ]
    manager.sync_records(desired_records)

    removed = wait_for_record_absence(api, removed_test["name"])
    assert removed


def test_dyndns_record_management(api: CloudflareAPI, dns_manager_module) -> None:
    """Test end-to-end dyndns record discovery and sync using Docker labels."""
    manager = dns_manager_module.CloudflareDNSManager(api.api_token, api.zone_name)
    manager.zone_id = api.zone_id
    manager.MANAGED_COMMENT = f"managed-by:dyndns-test-{uuid.uuid4().hex[:8]}"

    container = None
    record_name = None
    try:
        container = create_dyndns_test_container()
        time.sleep(2)

        discovered = dns_manager_module.get_docker_records(
            "192.168.1.100",
            {
                "docker_defaults": {
                    "proxied": False,
                    "ttl": 1,
                    "type": "A",
                }
            },
        )

        target = None
        for record in discovered:
            if record.get("container") == container.name:
                target = record
                break

        assert target is not None
        assert target["proxied"] is True
        assert target["type"] == "A"
        assert target["content"]

        record_name = target["name"]
        expected_ip = target["content"]

        manager.sync_records([target])
        matched, _ = wait_for_record_content(api, record_name, expected_ip, 30)
        assert matched

    finally:
        if record_name:
            existing = api.get_record(record_name)
            if existing:
                api.delete_record(existing["id"])
        if container is not None:
            cleanup_test_containers([container])


def cleanup_test_records(api: CloudflareAPI, record_names: List[str]):
    """Clean up test DNS records"""
    log_test("Cleanup", "INFO", "Removing test DNS records...")

    for name in record_names:
        record = api.get_record(name)
        if record:
            if api.delete_record(record["id"]):
                log_test(f"Cleanup: {name}", "PASS", "Deleted")
            else:
                log_test(f"Cleanup: {name}", "FAIL", "Failed to delete")
        else:
            log_test(f"Cleanup: {name}", "INFO", "Not found (already clean)")


def cleanup_stale_test_records(api: CloudflareAPI, dns_manager_module) -> None:
    """Remove any leftover test records from previous runs."""
    manager = dns_manager_module.CloudflareDNSManager(api.api_token, api.zone_name)
    manager.zone_id = api.zone_id
    existing = manager.get_existing_records()

    prefixes = (
        "cf-test-minimal-",
        "cf-test-custom-subdomain-",
        "cf-test-custom-ip-",
        "testsubdomain-",
        "traefik-",
    )

    for record in existing.values():
        name = record.get("name", "")
        if not any(name.startswith(f"{prefix}") for prefix in prefixes):
            continue
        manager.delete_record(record["id"], name)


def main():
    print("\n" + "=" * 60)
    print(f"{Colors.BLUE}Cloudflare DNS Manager Test Suite{Colors.RESET}")
    print("=" * 60 + "\n")

    # Check if running interactively
    interactive = sys.stdin.isatty()

    # Read API token
    api_token = read_api_token()
    api = CloudflareAPI(api_token, CF_ZONE_NAME)

    # Get zone ID
    log_test("Cloudflare API", "INFO", "Connecting to Cloudflare...")
    if api.get_zone_id():
        log_test("Cloudflare API", "PASS", f"Connected to zone: {CF_ZONE_NAME}")
    else:
        log_test("Cloudflare API", "FAIL", "Failed to get zone ID")
        sys.exit(1)

    print()

    tests = []
    containers = []
    record_names = []
    try:
        tests, containers = setup_test_containers()
        record_names = [test["name"] for test in tests]
        # Test 1: Docker containers
        print(f"{Colors.YELLOW}Test 1: Docker Container Status{Colors.RESET}")
        print("-" * 60)
        containers_ok = test_docker_containers(containers)
        print()

        if not containers_ok:
            log_test("Overall", "FAIL", "Not all test containers are running")
            print("\nRun: docker compose up -d")
            sys.exit(1)

        # Test 2: DNS records
        print(f"{Colors.YELLOW}Test 2: DNS Record Creation{Colors.RESET}")
        print("-" * 60)
        passed, failed = run_dns_record_checks(
            api, tests, timeout_seconds=30, phase="create"
        )
        print()

        # Summary
        print("=" * 60)
        print(f"{Colors.BLUE}Test Summary{Colors.RESET}")
        print("=" * 60)
        print(
            f"Containers: {Colors.GREEN}OK{Colors.RESET}"
            if containers_ok
            else f"Containers: {Colors.RED}FAILED{Colors.RESET}"
        )
        print(
            f"DNS Records: {Colors.GREEN}{passed} passed{Colors.RESET}, {Colors.RED}{failed} failed{Colors.RESET}"
        )

        if failed == 0 and containers_ok:
            print(f"\n{Colors.GREEN}✓ All tests passed!{Colors.RESET}\n")
            exit_code = 0
        else:
            print(f"\n{Colors.RED}✗ Some tests failed{Colors.RESET}\n")
            exit_code = 1

        # Ask about cleanup
        if interactive:
            print("-" * 60)
            cleanup = input("Clean up test DNS records? [y/N]: ").lower().strip()
            if cleanup in ["y", "yes"]:
                print()
                cleanup_test_records(api, record_names)
                print()
        else:
            print(
                f"\n{Colors.YELLOW}Note: Run interactively to clean up test records{Colors.RESET}"
            )
            if record_names:
                print(f"Or manually delete: {', '.join(record_names)}\n")

        sys.exit(exit_code)
    finally:
        cleanup_test_containers(containers)


if __name__ == "__main__":
    main()
