"""
Pytest configuration and shared fixtures.
"""

import os
import pytest
import docker
import time
from typing import Generator

@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig) -> str:
    """Get the docker-compose file path."""
    return os.path.join(
        str(pytestconfig.rootdir),
        "tests",
        "docker-compose.test.yaml"
    )

@pytest.fixture(scope="session")
def docker_compose_project_name() -> str:
    """Get the docker-compose project name."""
    return "apocacache_test"

@pytest.fixture(scope="session")
def mock_kiwix_server(docker_services) -> str:
    """Start the mock Kiwix server and wait for it to be ready."""
    port = docker_services.port_for("mock-kiwix-server", 80)
    url = f"http://localhost:{port}"
    
    docker_services.wait_until_responsive(
        timeout=30.0,
        pause=0.1,
        check=lambda: is_server_ready(url)
    )
    
    return url

def is_server_ready(url: str) -> bool:
    """Check if the mock server is ready."""
    import requests
    try:
        response = requests.get(f"{url}/health")
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        return False

@pytest.fixture(scope="session")
def docker_services(
    docker_compose_file: str,
    docker_compose_project_name: str
) -> Generator:
    """Start all services from the docker-compose file."""
    client = docker.from_env()
    
    # Pull required images
    client.images.pull("nginx:alpine")
    client.images.pull("python:3.11-slim")
    
    # Start services
    command = f"docker-compose -f {docker_compose_file} -p {docker_compose_project_name} up -d"
    os.system(command)
    
    # Wait for services to be ready
    time.sleep(5)
    
    yield
    
    # Cleanup
    command = f"docker-compose -f {docker_compose_file} -p {docker_compose_project_name} down -v"
    os.system(command) 