# ⚠️ WORK IN PROGRESS
This project is currently under active development. Features may be incomplete or subject to change.

# ApocaCache

A robust library maintainer for offline content caching, specifically designed to manage and maintain Kiwix ZIM files. This project helps maintain an up-to-date offline cache of educational content, documentation, and knowledge bases.

## Features

- **Automated Content Management**: Automatically downloads and maintains ZIM files from Kiwix servers
- **Smart Updates**: Only downloads new or updated content based on file dates and sizes
- **Language Filtering**: Configurable language filtering to download content in specific languages
- **Concurrent Downloads**: Manages multiple downloads with configurable concurrency limits
- **Robust Error Handling**: Implements retries, timeouts, and cleanup for failed downloads
- **Progress Monitoring**: Detailed logging and progress tracking for downloads
- **Apache Directory Parsing**: Efficient parsing of Apache directory listings with caching
- **State Management**: Maintains download state and content metadata

## Project Structure

```
ApocaCache/
├── library-maintainer/
│   ├── src/
│   │   ├── content_manager.py    # Core content management logic
│   │   ├── config.py            # Configuration handling
│   │   ├── monitoring.py        # Monitoring and metrics
│   │   └── main.py             # Application entry point
│   ├── tests/
│   │   ├── integration/        # Integration tests
│   │   └── unit/              # Unit tests
│   ├── Dockerfile             # Container definition
│   └── requirements.txt       # Python dependencies
├── docker-compose.yaml        # Service orchestration
└── README.md                 # This file
```

## Configuration

### Environment Variables

- `BASE_URL`: Kiwix download server URL (default: "https://download.kiwix.org/zim/")
- `LANGUAGE_FILTER`: Comma-separated list of language codes (e.g., "eng,en")
- `DOWNLOAD_ALL`: Whether to download all content regardless of filters (default: false)
- `CONTENT_PATTERN`: Regex pattern for content matching (default: ".*")
- `SCAN_SUBDIRS`: Whether to scan subdirectories (default: false)
- `UPDATE_SCHEDULE`: Cron-style schedule for updates (default: "0 2 1 * *")
- `EXCLUDED_DIRS`: Comma-separated list of directories to exclude from scanning

### Download List Configuration

Create a `download-list.yaml` in your data directory:

```yaml
options:
  max_concurrent_downloads: 2
  retry_attempts: 3
  verify_downloads: true
  cleanup_incomplete: true

content:
  - name: "wikipedia"
    language: "eng"
    category: "encyclopedia"
    description: "English Wikipedia"
  - name: "devdocs"
    language: "en"
    category: "documentation"
    description: "Developer Documentation"
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ApocaCache.git
cd ApocaCache
```

2. Build the container:
```bash
docker-compose build
```

3. Create your configuration:
```bash
mkdir -p data
cp example-download-list.yaml data/download-list.yaml
# Edit data/download-list.yaml with your content preferences
```

4. Start the service:
```bash
docker-compose up -d
```

## Development

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Make (optional, for development commands)

### Setting up Development Environment

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
```

2. Install dependencies:
```bash
pip install -r library-maintainer/requirements.txt
pip install -r library-maintainer/tests/requirements.test.txt
```

### Running Tests

```bash
# Run all tests
docker-compose -f tests/docker-compose.test.yaml run --rm test-runner pytest

# Run specific test file
docker-compose -f tests/docker-compose.test.yaml run --rm test-runner pytest tests/integration/test_content_manager.py

# Run with coverage
docker-compose -f tests/docker-compose.test.yaml run --rm test-runner pytest --cov=src tests/
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Kiwix](https://www.kiwix.org/) for providing the ZIM file infrastructure
- The open-source community for various libraries used in this project

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