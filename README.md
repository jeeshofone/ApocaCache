# ⚠️ WORK IN PROGRESS
This project is currently under active development. Features may be incomplete or subject to change.

# ApocaCache

A distributed caching system for Kiwix ZIM files.

## About the Name

ApocaCache (Apocalypse + Cache) is designed with disaster preparedness in mind. In a world where internet connectivity cannot be taken for granted, whether due to natural disasters, infrastructure failures, or other catastrophic events, having access to human knowledge becomes crucial.

This project enables you to:
- Maintain an offline copy of Wikipedia and other educational resources
- Automatically sync and update content when connectivity is available
- Run on any hardware, from a Raspberry Pi to a data center
- Serve content reliably even in disconnected environments
- Deploy in containerized environments for easy maintenance and portability

Think of it as your "knowledge bunker" - always ready, always accessible, regardless of what happens to the broader internet infrastructure.

## Project Status (2025-02-02)
All integration tests are now passing with improved stability. The library maintainer component has been enhanced with better file matching logic, content state management, and proper permission handling.

### Components
- **Library Maintainer**: Manages ZIM file downloads and library.xml generation
  - Content state management with atomic updates
  - Concurrent downloads with semaphore control
  - Progress tracking and monitoring
  - Enhanced file matching logic
  - Improved error handling
  - Proper permission handling with configurable UID/GID
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
- Added proper permission handling with configurable UID/GID

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

# Set up the kiwix directory with proper permissions
chmod +x setup_kiwix_dir.sh
./setup_kiwix_dir.sh

# Build and start the services (this will use your current user's UID/GID)
export UID=$(id -u)
export GID=$(id -g)
docker-compose build
docker-compose up -d
```

### Example Configurations

#### Download All English Content
Use the provided example in `examples/docker-compose-english-all.yaml`:

```bash
# Set up permissions
chmod +x setup_kiwix_dir.sh
./setup_kiwix_dir.sh

# Build and run with your user's UID/GID
export UID=$(id -u)
export GID=$(id -g)
docker-compose -f examples/docker-compose-english-all.yaml build
docker-compose -f examples/docker-compose-english-all.yaml up -d
```

The English-all configuration includes:
- Language filter set to 'en' (ISO 639-1 code)
- Automatic daily updates at 2 AM
- Concurrent download management
- Download verification
- Proper permission handling using host UID/GID
- Kiwix web interface accessible at http://localhost:3119

More example configurations can be found in the `examples/` directory.

## Configuration

### Environment Variables

- `LANGUAGE_FILTER`: Filter content by language codes (e.g., "en,es" using ISO 639-1 codes)
- `UPDATE_SCHEDULE`: Cron expression for update schedule (default: "0 2 1 * *")
- `DOWNLOAD_ALL`: Boolean flag to download all available content (default: false)
- `KIWIX_SERVER_URL`: URL for the Kiwix server (default: "http://kiwix-serve")
- `UID`: User ID for container processes (defaults to current user's UID)
- `GID`: Group ID for container processes (defaults to current user's GID)

### Custom Download List

Create a `download-list.yaml` file:

```yaml
content:
  - name: "wikipedia_en"
    language: "en"
    category: "wikipedia"
  - name: "wiktionary_es"
    language: "es"
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

## First Run Setup

This project is designed to work immediately after cloning. The repository has been pre-configured with default settings to ensure a smooth first run:

- A default library file is provided at `examples/kiwix/library.xml`. This file contains a default entry for the Wikipedia (English, no pics) zim file from the official Kiwix server, ensuring that the library maintainer finds content to download.
- The Docker Compose configuration in `examples/docker-compose-english-all.yaml` maps the `./kiwix` directory to `/data` in the containers, so the default library file is automatically used.
- To start the project, run:

  docker compose -f examples/docker-compose-english-all.yaml up

- The library maintainer service will parse the default library file and trigger a download of the content (if not already present) from the official Kiwix server.

If you encounter any issues on first run, please ensure that the volume mappings and file permissions are correctly configured, and verify that the default entries in `examples/kiwix/library.xml` suit your needs.

--- 