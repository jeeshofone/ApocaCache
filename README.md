# ApocaCache

A distributed caching system for Kiwix ZIM files.

## Project Status (2025-02-02 21:50)
Integration tests are now fully implemented and passing. The library maintainer component is stable and ready for feature enhancements.

### Components
- **Library Maintainer**: Manages ZIM file downloads and library.xml generation
  - Content state management
  - Concurrent downloads
  - Progress tracking
  - Atomic updates
- **Mock Kiwix Server**: Test infrastructure for integration testing
  - Directory listing
  - Content serving
  - Health checks

### Recent Achievements
- All integration tests passing
- Improved mock server configuration
- Enhanced content manager reliability
- Fixed async fixture handling
- Implemented atomic state updates
- Added comprehensive error handling

### Current Development Focus
- Performance optimization
- Monitoring enhancements
- Content validation
- Documentation improvements

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
- Python 3.11+

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