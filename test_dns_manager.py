#!/usr/bin/env python3
"""
Test suite for Cloudflare DNS Manager
"""
import os
import sys
import json
import time
import docker
import requests
from typing import List, Dict

# Configuration
CF_API_TOKEN_FILE = os.getenv("CF_API_TOKEN_FILE", "/run/secrets/cf_api_token")
CF_ZONE_NAME = os.getenv("CF_ZONE_NAME", "example.com")
TEST_SLEEP = 5  # Seconds to wait for DNS sync

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

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
            "Content-Type": "application/json"
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
        with open(CF_API_TOKEN_FILE, 'r') as f:
            return f.read().strip()
    except Exception as e:
        print(f"{Colors.RED}Failed to read API token: {e}{Colors.RESET}")
        sys.exit(1)

def get_test_containers() -> List[str]:
    """Get list of test container names"""
    return [
        "cf-test-minimal",
        "cf-test-custom-subdomain",
        "cf-test-custom-ip",
        "cf-test-traefik-host"
    ]

def test_docker_containers():
    """Test that test containers are running"""
    log_test("Docker Connection", "INFO", "Checking test containers...")
    
    try:
        client = docker.from_env()
        test_containers = get_test_containers()
        
        running_containers = []
        for container_name in test_containers:
            try:
                container = client.containers.get(container_name)
                if container.status == "running":
                    running_containers.append(container_name)
                    log_test(f"Container: {container_name}", "PASS", f"Status: {container.status}")
                else:
                    log_test(f"Container: {container_name}", "FAIL", f"Status: {container.status}")
            except docker.errors.NotFound:
                log_test(f"Container: {container_name}", "FAIL", "Not found")
        
        return len(running_containers) == len(test_containers)
    
    except Exception as e:
        log_test("Docker Connection", "FAIL", str(e))
        return False

def test_dns_records(api: CloudflareAPI):
    """Test that DNS records are created correctly"""
    log_test("DNS Records", "INFO", f"Waiting {TEST_SLEEP}s for sync...")
    time.sleep(TEST_SLEEP)
    
    tests = [
        {
            "name": "cf-test-minimal",
            "expected_ip": "192.168.1.189",
            "description": "Minimal label configuration"
        },
        {
            "name": "testsubdomain",
            "expected_ip": "192.168.1.189",
            "description": "Custom subdomain override"
        },
        {
            "name": "cf-test-custom-ip",
            "expected_ip": "10.0.0.100",
            "description": "Custom IP address"
        },
        {
            "name": "cf-test-traefik-host",
            "expected_ip": "192.168.1.189",
            "description": "Container name fallback (Traefik extraction needs proper router)"
        }
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        record = api.get_record(test["name"])
        
        if record:
            if record.get("content") == test["expected_ip"]:
                log_test(
                    f"Record: {test['name']}",
                    "PASS",
                    f"IP: {record.get('content')} - {test['description']}"
                )
                passed += 1
            else:
                log_test(
                    f"Record: {test['name']}",
                    "FAIL",
                    f"Expected {test['expected_ip']}, got {record.get('content')}"
                )
                failed += 1
        else:
            log_test(
                f"Record: {test['name']}",
                "FAIL",
                f"Record not found - {test['description']}"
            )
            failed += 1
    
    return passed, failed

def cleanup_test_records(api: CloudflareAPI):
    """Clean up test DNS records"""
    log_test("Cleanup", "INFO", "Removing test DNS records...")
    
    test_names = [
        "cf-test-minimal",
        "testsubdomain",
        "cf-test-custom-ip",
        "cf-test-traefik-host"
    ]
    
    for name in test_names:
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
    import sys
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
    
    # Test 1: Docker containers
    print(f"{Colors.YELLOW}Test 1: Docker Container Status{Colors.RESET}")
    print("-" * 60)
    containers_ok = test_docker_containers()
    print()
    
    if not containers_ok:
        log_test("Overall", "FAIL", "Not all test containers are running")
        print("\nRun: docker compose up -d")
        sys.exit(1)
    
    # Test 2: DNS records
    print(f"{Colors.YELLOW}Test 2: DNS Record Creation{Colors.RESET}")
    print("-" * 60)
    passed, failed = test_dns_records(api)
    print()
    
    # Summary
    print("=" * 60)
    print(f"{Colors.BLUE}Test Summary{Colors.RESET}")
    print("=" * 60)
    print(f"Containers: {Colors.GREEN}OK{Colors.RESET}" if containers_ok else f"Containers: {Colors.RED}FAILED{Colors.RESET}")
    print(f"DNS Records: {Colors.GREEN}{passed} passed{Colors.RESET}, {Colors.RED}{failed} failed{Colors.RESET}")
    
    total_tests = passed + failed
    if failed == 0 and containers_ok:
        print(f"\n{Colors.GREEN}✓ All tests passed!{Colors.RESET}\n")
        exit_code = 0
    else:
        print(f"\n{Colors.RED}✗ Some tests failed{Colors.RESET}\n")
        exit_code = 1
    
    # Ask about cleanup
    if interactive:
        print("-" * 60)
        cleanup = input(f"Clean up test DNS records? [y/N]: ").lower().strip()
        if cleanup in ['y', 'yes']:
            print()
            cleanup_test_records(api)
            print()
    else:
        print(f"\n{Colors.YELLOW}Note: Run interactively to clean up test records{Colors.RESET}")
        print(f"Or manually delete: cf-test-minimal, testsubdomain, cf-test-custom-ip, traefik-test\n")
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
