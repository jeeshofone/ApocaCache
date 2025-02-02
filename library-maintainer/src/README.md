# Library Maintainer

The library maintainer is a core component of ApocaCache that manages the downloading, updating, and organization of Kiwix ZIM files. It works in conjunction with the Kiwix-serve container to provide a complete offline Wikipedia and knowledge solution.

## Architecture

The library maintainer consists of several Python modules working together:

### 1. Main Service (`main.py`)
- Entry point for the service
- Manages the service lifecycle
- Handles scheduling and coordination
- Implements graceful shutdown
- Configures structured logging

Key components:
```python
class LibraryMaintainerService:
    def __init__(self):
        self.config = Config()
        self.content_manager = ContentManager(self.config)
        self.library_manager = LibraryManager(self.config)
```

### 2. Configuration Management (`config.py`)
- Handles environment variables
- Parses YAML configuration
- Manages content filtering
- Provides configuration dataclasses

Configuration options:
```python
@dataclass
class ContentOptions:
    max_concurrent_downloads: int = 2
    retry_attempts: int = 3
    verify_downloads: bool = True
    cleanup_incomplete: bool = True
```

### 3. Content Manager (`content_manager.py`)
- Downloads ZIM files from Kiwix servers
- Manages content state
- Implements concurrent downloads
- Handles file verification
- Provides cleanup functionality

Key features:
- Asynchronous downloads with progress tracking
- Concurrent download limiting
- State persistence
- Download verification
- Temporary file cleanup

### 4. Library Manager (`library_manager.py`)
- Generates library.xml for Kiwix-serve
- Extracts ZIM metadata
- Manages library updates
- Handles atomic file operations

XML structure:
```xml
<library version="20110515">
  <book id="kiwix_CONTENT_NAME">
    <title>CONTENT_NAME</title>
    <creator>CREATOR</creator>
    <date>DATE</date>
    <!-- Additional metadata -->
  </book>
</library>
```

### 5. Monitoring (`monitoring.py`)
- Provides Prometheus metrics
- Tracks download progress
- Monitors library size
- Records operation durations

Available metrics:
- `apocacache_content_downloads_total`
- `apocacache_content_size_bytes`
- `apocacache_update_duration_seconds`
- `apocacache_library_size_bytes`

## Flow of Operations

1. Service Startup:
   - Load configuration
   - Initialize components
   - Setup monitoring
   - Schedule updates

2. Content Update:
   ```
   ┌─────────────────┐
   │ Update Trigger  │
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │  Fetch Content  │
   │     List       │
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ Filter Content  │
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │   Download &    │
   │    Verify      │
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ Update Library  │
   │      XML       │
   └─────────────────┘
   ```

3. Monitoring:
   - Track download progress
   - Record metrics
   - Log operations

## Configuration

### Environment Variables
- `LANGUAGE_FILTER`: Filter content by language codes
- `UPDATE_SCHEDULE`: Cron expression for updates
- `DOWNLOAD_ALL`: Boolean to download all content

### YAML Configuration
```yaml
content:
  - name: "wikipedia_en_all_mini"
    language: "eng"
    category: "wikipedia"
    description: "Wikipedia Mini in English"

options:
  max_concurrent_downloads: 2
  retry_attempts: 3
  verify_downloads: true
  cleanup_incomplete: true
```

## Development

### Prerequisites
- Python 3.8+
- Required packages in requirements.txt
- Docker for containerization

### Testing
```bash
# Run unit tests
python -m pytest tests/

# Run with coverage
python -m pytest --cov=src tests/
```

### Adding New Features
1. Update configuration if needed
2. Implement feature in relevant module
3. Add monitoring metrics
4. Update tests
5. Document changes

## Future Improvements

1. ZIM Metadata Extraction:
   - Implement proper metadata extraction from ZIM files
   - Add support for additional metadata fields

2. Download Optimization:
   - Add download resume capability
   - Implement better verification
   - Optimize concurrent downloads

3. Content Management:
   - Add content indexing
   - Implement better cleanup
   - Add content validation

4. Monitoring:
   - Add more detailed metrics
   - Implement better error tracking
   - Add performance monitoring 