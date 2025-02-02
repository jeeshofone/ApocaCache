#!/bin/bash
# run_tests.sh
# This script builds Docker images without cache and runs the complete test suite inside Docker containers.
# It sets the TESTING environment variable so that tests use the sample ZIM file from GitHub.
#
# Usage: ./run_tests.sh
# Ensure Docker and docker-compose are installed and run this script from the project root.

set -euo pipefail

# Set the TESTING environment variable
export TESTING=true

echo "Building Docker images without cache..."
docker-compose -f library-maintainer/tests/docker-compose.test.yaml build --no-cache

echo "Running tests against production library-maintainer container..."
docker-compose -f library-maintainer/tests/docker-compose.test.yaml run --rm -e PYTHONPATH=/app/src test-runner pytest /app/tests/integration -v

echo "Bringing down Docker containers..."
docker-compose -f library-maintainer/tests/docker-compose.test.yaml down

echo "Test suite completed." 