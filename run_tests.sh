#!/bin/bash
# Test runner script for Cloudflare DNS Manager

set -e

echo "======================================================================"
echo "Cloudflare DNS Manager - Test Runner"
echo "======================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "docker-compose.yaml" ]; then
    echo -e "${RED}Error: docker-compose.yaml not found${NC}"
    echo "Please run this script from /opt/cloudflare-dns-manager"
    exit 1
fi

# Check if CF API token exists
if [ ! -f "/opt/traefik/secrets/cf_dns_api_token" ]; then
    echo -e "${RED}Error: Cloudflare API token not found${NC}"
    echo "Expected: /opt/traefik/secrets/cf_dns_api_token"
    exit 1
fi

echo -e "${YELLOW}Step 1: Starting test containers...${NC}"
docker compose up -d
echo ""

echo -e "${YELLOW}Step 2: Waiting for DNS manager to start...${NC}"
sleep 5
echo ""

echo -e "${YELLOW}Step 3: Checking DNS manager logs...${NC}"
docker logs cloudflare-dns-manager --tail 20
echo ""

echo -e "${YELLOW}Step 4: Running test suite...${NC}"
echo ""

# Run the test suite in a temporary container
docker run --rm \
    -v "$(pwd)/test_dns_manager.py:/test_dns_manager.py:ro" \
    -v "/opt/traefik/secrets/cf_dns_api_token:/run/secrets/cf_api_token:ro" \
    -v "/var/run/docker.sock:/var/run/docker.sock:ro" \
    -e CF_API_TOKEN_FILE=/run/secrets/cf_api_token \
    -e CF_ZONE_NAME=example.com \
    --network host \
    python:3.11-alpine \
    sh -c "pip install --no-cache-dir requests docker && python /test_dns_manager.py"

TEST_EXIT_CODE=$?

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}======================================================================"
    echo -e "✓ All tests passed!"
    echo -e "======================================================================${NC}"
else
    echo -e "${RED}======================================================================"
    echo -e "✗ Some tests failed"
    echo -e "======================================================================${NC}"
fi

echo ""
echo "To view DNS manager logs:"
echo "  docker logs cloudflare-dns-manager -f"
echo ""
echo "To stop test containers:"
echo "  docker compose down"
echo ""

exit $TEST_EXIT_CODE
