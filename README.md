# ApocaCache

A distributed caching system for Kiwix ZIM files.

## Project Status (2025-02-02)
Currently in development, focusing on the library maintainer component. Integration tests are being implemented and debugged.

### Components
- **Library Maintainer**: Manages ZIM file downloads and library.xml generation
- **Mock Kiwix Server**: Test infrastructure for integration testing

### Current Development Focus
- Integration testing of content download functionality
- Mock server configuration for testing
- Async fixture handling in pytest

### Recent Changes
- Fixed async fixture configuration
- Updated mock server configuration
- Improved content manager URL handling
- Enhanced test infrastructure

## Development Setup

### Prerequisites
- Python 3.11+
- Docker and Docker Compose
- pytest for testing

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
│   ├── content_manager.py
│   ├── library_manager.py
│   └── config.py
├── tests/
│   ├── integration/
│   │   ├── test_content_manager.py
│   │   └── test_library_manager.py
│   └── fixtures/
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

## Quick Start

```bash
# Clone the repository
git clone https://github.com/jeeshofone/ApocaCache.git
cd ApocaCache

# Start the services
docker-compose up -d
```

## Configuration

### Environment Variables

- `LANGUAGE_FILTER`: Filter content by language codes (e.g., "eng,spa")
- `UPDATE_SCHEDULE`: Cron expression for update schedule (default: "0 2 1 * *")
- `DOWNLOAD_ALL`: Boolean flag to download all available content (default: false)

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

## Development

### Prerequisites

- Docker
- Docker Compose
- Python 3.8+

### Building

```bash
# Build for multiple architectures
./library-maintainer/build.sh
```

### Testing

```bash
cd library-maintainer
python -m pytest
```

## License

[MIT License](LICENSE)

## Security

Please report security issues to [security contact]. 