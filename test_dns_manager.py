#!/usr/bin/env python3
"""
Test suite for Cloudflare DNS Manager
"""
import os
import random
import sys
import time
import uuid
from typing import Dict, List, Tuple

import docker
import pytest
import requests

# Configuration
CF_API_TOKEN_FILE = os.getenv("CF_API_TOKEN_FILE", "/run/secrets/cf_api_token")
CF_ZONE_NAME = os.getenv("CF_ZONE_NAME", "example.com")
CF_ZONE_ID = os.getenv("CF_ZONE_ID")
TEST_SLEEP = 5  # Seconds to wait for DNS sync
REQUIRE_CF_TESTS = os.getenv("REQUIRE_CF_TESTS", "").lower() in ("1", "true", "yes")


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"


def log_test(name: str, status: str, message: str = ""):
    """Pretty print test results"""
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
        self.zone_id = None

    def get_zone_id(self) -> str:
        """Get zone ID"""
        if self.zone_id:
            return self.zone_id

        url = f"{self.base_url}/zones"
        params = {"name": self.zone_name}
        response = requests.get(url, headers=self.headers, params=params)

        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("result"):
                self.zone_id = data["result"][0]["id"]
                return self.zone_id
        return None

    def get_record(self, name: str, record_type: str = "A") -> Dict:
        """Get a specific DNS record"""
        if not self.zone_id:
            self.get_zone_id()

        full_name = f"{name}.{self.zone_name}" if name != "@" else self.zone_name

        url = f"{self.base_url}/zones/{self.zone_id}/dns_records"
        params = {"name": full_name, "type": record_type}
        response = requests.get(url, headers=self.headers, params=params)

        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("result"):
                return data["result"][0] if data["result"] else None
        return None

    def delete_record(self, record_id: str) -> bool:
        """Delete a DNS record"""
        if not self.zone_id:
            self.get_zone_id()

        url = f"{self.base_url}/zones/{self.zone_id}/dns_records/{record_id}"
        response = requests.delete(url, headers=self.headers)
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
    """Generate a random private IPv4 address."""
    range_choice = random.choice(["10", "172", "192"])
    if range_choice == "10":
        return f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
    if range_choice == "172":
        return (
            f"172.{random.randint(16, 31)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
        )
    return f"192.168.{random.randint(0, 255)}.{random.randint(1, 254)}"


def setup_test_containers() -> Tuple[List[dict], List[docker.models.containers.Container]]:
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
            labels[
                f"traefik.http.routers.{container_name}.rule"
            ] = f"Host(`{test_def['subdomain']}.{CF_ZONE_NAME}`)"

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


def cleanup_test_containers(containers: List[docker.models.containers.Container]) -> None:
    """Stop and remove temporary test containers."""
    for container in containers:
        try:
            container.remove(force=True)
            log_test(f"Container cleanup: {container.name}", "PASS", "Removed")
        except Exception as e:
            log_test(f"Container cleanup: {container.name}", "FAIL", str(e))


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
        return api_client
    if not api_client.get_zone_id():
        if REQUIRE_CF_TESTS:
            pytest.fail("Failed to get zone ID")
        pytest.skip("Failed to get zone ID")
    return api_client


@pytest.fixture(scope="module", autouse=True)
def cleanup_records(api: CloudflareAPI, tests: List[Dict]):
    record_names = [test["name"] for test in tests]
    yield
    cleanup_test_records(api, record_names)


def test_docker_containers(containers: List[docker.models.containers.Container]) -> bool:
    """Test that test containers are running"""
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
    return result


def test_dns_records(api: CloudflareAPI, tests: List[Dict]):
    """Test that DNS records are created correctly"""
    log_test("DNS Records", "INFO", f"Waiting {TEST_SLEEP}s for sync...")
    time.sleep(TEST_SLEEP)

    passed = 0
    failed = 0

    for test in tests:
        record = api.get_record(test["name"])

        if record:
            if record.get("content") == test["expected_ip"]:
                log_test(
                    f"Record: {test['name']}",
                    "PASS",
                    f"IP: {record.get('content')} - {test['description']}",
                )
                passed += 1
            else:
                log_test(
                    f"Record: {test['name']}",
                    "FAIL",
                    f"Expected {test['expected_ip']}, got {record.get('content')}",
                )
                failed += 1
        else:
            log_test(
                f"Record: {test['name']}",
                "FAIL",
                f"Record not found - {test['description']}",
            )
            failed += 1

    assert failed == 0
    return passed, failed


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
        passed, failed = test_dns_records(api, tests)
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
