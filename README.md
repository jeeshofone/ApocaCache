# ApocaCache

A distributed caching system for Kiwix ZIM files.

## Project Status ($(date '+%Y-%m-%d %H:%M'))
All integration tests are now passing with improved stability. The library maintainer component has been enhanced with better file matching logic and content state management.

### Components
- **Library Maintainer**: Manages ZIM file downloads and library.xml generation
  - Content state management with atomic updates
  - Concurrent downloads with semaphore control
  - Progress tracking and monitoring
  - Enhanced file matching logic
  - Improved error handling
- **Mock Kiwix Server**: Test infrastructure for integration testing
  - Directory listing
  - Content serving
  - Health checks
  - Test file provisioning

### Recent Achievements
- Fixed content state update mechanism
- Improved file matching logic
- Enhanced logging and error handling
- All integration tests passing
- Verified concurrent download functionality
- Confirmed atomic state updates

### Current Development Focus
- Performance optimization
- Monitoring enhancements
- Content validation
- Documentation improvements
- Example configurations

## Quick Start

### Basic Setup
```bash
# Clone the repository
git clone https://github.com/jeeshofone/ApocaCache.git
cd ApocaCache

# Create data directory
sudo mkdir -p /kiwix
sudo chown -R 1000:1000 /kiwix

# Build and start the services
docker-compose build
docker-compose up -d
```

### Example Configurations

#### Download All English Content
Create a `docker-compose.yaml` file:

```yaml
version: '3.8'

services:
  library-maintainer:
    build:
      context: ../library-maintainer
      dockerfile: Dockerfile
    environment:
      - LANGUAGE_FILTER=eng
      - DOWNLOAD_ALL=true
      - UPDATE_SCHEDULE=0 2 * * *  # Run at 2 AM daily
    volumes:
      - /kiwix:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  kiwix-serve:
    image: ghcr.io/kiwix/kiwix-serve:latest
    ports:
      - "8080:8080"
    volumes:
      - /kiwix:/data:ro
    depends_on:
      library-maintainer:
        condition: service_healthy
    command: --library /data/library.xml
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/catalog"]
      interval: 30s
      timeout: 10s
      retries: 3
```

More example configurations can be found in the `examples/` directory.

## Configuration

### Environment Variables

- `LANGUAGE_FILTER`: Filter content by language codes (e.g., "eng,spa")
- `UPDATE_SCHEDULE`: Cron expression for update schedule (default: "0 2 1 * *")
- `DOWNLOAD_ALL`: Boolean flag to download all available content (default: false)
- `KIWIX_SERVER_URL`: URL for the Kiwix server (default: "http://kiwix-serve")

### Custom Download List

Create a `download-list.yaml` file:

```yaml
content:
  - name: "wikipedia_en"
    language: "eng"
    category: "wikipedia"
  - name: "wiktionary_es"
    language: "spa"
    category: "wiktionary"
```

## Development Setup

### Prerequisites
- Python 3.11+
- Docker and Docker Compose
- pytest for testing

### Building Images
```bash
# Build all images
docker-compose build

# Build specific service
docker-compose build library-maintainer
```

### Running Tests
```bash
cd library-maintainer
docker-compose -f tests/docker-compose.test.yaml down -v
docker-compose -f tests/docker-compose.test.yaml build --no-cache
docker-compose -f tests/docker-compose.test.yaml run --rm integration-tests pytest tests/ -v
```

## Project Structure
```
library-maintainer/
├── src/
│   ├── content_manager.py  # Content download and management
│   ├── library_manager.py  # Library.xml generation
│   └── config.py          # Configuration handling
├── tests/
│   ├── integration/       # Integration tests
│   │   ├── test_content_manager.py
│   │   └── test_library_manager.py
│   └── fixtures/         # Test fixtures
│       └── mock-kiwix-server/
└── docker-compose.test.yaml
```

## Contributing
Currently in active development. See todo.md for current tasks and progress.

## Overview

ApocaCache automates the process of downloading, managing, and serving Kiwix ZIM files through a containerized solution. It provides a reliable way to maintain an up-to-date offline Wikipedia and other Kiwix-supported content.

### Components

1. **Library Maintainer Container**: Manages the downloading and updating of Kiwix ZIM files
   - Automated content updates
   - Content filtering by language
   - Custom download lists via YAML configuration
   - Library.xml management

2. **Kiwix Serve Container**: Serves the content using the official Kiwix server
   - Based on ghcr.io/kiwix/kiwix-serve:latest
   - Configured to serve content from shared volume

## License

[MIT License](LICENSE)

## Security

Please report security issues to [security contact].

## Running Tests

To run the complete test suite within Docker containers, follow these steps:

1. Ensure Docker and docker-compose are installed on your system.
2. Grant executable permission to the test script (if not already set):
   chmod +x run_tests.sh
3. Execute the test script:
   ./run_tests.sh

The run_tests.sh script will:
- Build Docker images without using the cache.
- Set the TESTING environment variable to "true" so that tests use the sample ZIM file from [https://github.com/openzim/zim-tools/blob/main/test/data/zimfiles/good.zim](https://github.com/openzim/zim-tools/blob/main/test/data/zimfiles/good.zim).
- Run the test suite using the docker-compose configuration from library-maintainer/tests/docker-compose.test.yaml.
- Automatically shut down the Docker containers upon completion. 