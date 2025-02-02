# ApocaCache

A containerized solution for hosting and managing Kiwix content libraries. ApocaCache consists of two main containers that work together to provide an automated, self-updating Kiwix server.

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

## Contributing

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) for details.

## Security

Please report security issues to [security contact].

## Project Status

Last updated: $(date '+%Y-%m-%d') 