"""
Integration tests for the content manager.
Tests the content manager's ability to download and manage ZIM files.
"""

import os
import pytest
import aiohttp
import asyncio
from datetime import datetime
from pytest_asyncio import fixture as async_fixture
import logging
import time
import structlog

from content_manager import ContentManager, ApacheDirectoryParser
from config import Config, ContentItem

# Set up logging with more detail for tests
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = structlog.get_logger()

@pytest.fixture(autouse=True)
def log_test(caplog):
    """Automatically log test names and results."""
    caplog.set_level(logging.DEBUG)
    yield
    # Log any errors or warnings after test
    if caplog.records:
        log.info("test.logs", records=[
            f"{r.levelname}: {r.message}" for r in caplog.records
        ])

@async_fixture(scope="function")
async def content_manager():
    """Create a content manager instance for testing."""
    config = Config()
    # Use the real Kiwix server
    config.base_url = "https://download.kiwix.org/zim/"
    # Set language filter to match English content
    config.language_filter = ["eng", "en"]
    config.content_pattern = ".*"  # Match all files
    config.scan_subdirs = True  # Enable subdirectory scanning
    manager = ContentManager(config)
    yield manager
    await manager.cleanup()

@async_fixture(scope="function")
async def directory_parser():
    """Create an ApacheDirectoryParser instance for testing."""
    return ApacheDirectoryParser()

def test_parse_size(content_manager):
    """Test parsing of human-readable sizes."""
    # Test various size formats
    assert content_manager._parse_size("1K") == 1024
    assert content_manager._parse_size("1.5K") == 1536
    assert content_manager._parse_size("1M") == 1024 * 1024
    assert content_manager._parse_size("1G") == 1024 * 1024 * 1024
    assert content_manager._parse_size("1T") == 1024 * 1024 * 1024 * 1024
    assert content_manager._parse_size("123") == 123
    assert content_manager._parse_size("-") == 0
    assert content_manager._parse_size("") == 0
    assert content_manager._parse_size("invalid") == 0

@pytest.mark.asyncio
async def test_directory_parser_caching(directory_parser):
    """Test that the directory parser caches results correctly."""
    test_url = "https://test.com"
    test_content = """
    <html><body><pre>
    <a href="test.zim">test.zim</a>                2024-01-01 12:00  1.5G
    </pre></body></html>
    """
    
    # First parse should cache
    entries1 = directory_parser.parse_directory_listing(test_content, test_url)
    assert len(entries1) == 1
    assert test_url in directory_parser.cache
    
    # Second parse should use cache
    entries2 = directory_parser.parse_directory_listing(test_content, test_url)
    assert entries1 == entries2
    
    # Wait for cache to expire
    time.sleep(0.1)  # Reduce test time by setting a short TTL
    directory_parser.cache_ttl = 0.05
    
    # Third parse should refresh cache
    entries3 = directory_parser.parse_directory_listing(test_content, test_url)
    assert len(entries3) == 1
    assert entries1 == entries3

@pytest.mark.asyncio
async def test_directory_parser_invalid_html(directory_parser):
    """Test that the directory parser handles invalid HTML gracefully."""
    test_url = "https://test.com"
    
    # Test with empty content
    assert len(directory_parser.parse_directory_listing("", test_url)) == 0
    
    # Test with malformed HTML
    assert len(directory_parser.parse_directory_listing("<html><body>", test_url)) == 0
    
    # Test with missing pre tag
    assert len(directory_parser.parse_directory_listing(
        "<html><body>No pre tag</body></html>", test_url)) == 0
    
    # Test with invalid date format
    entries = directory_parser.parse_directory_listing("""
    <html><body><pre>
    <a href="test.zim">test.zim</a>                invalid-date  1.5G
    </pre></body></html>
    """, test_url)
    assert len(entries) == 0

@pytest.mark.asyncio
async def test_get_available_content(content_manager):
    """Test fetching available content from Kiwix server."""
    try:
        content_list = await content_manager._get_available_content()
        assert len(content_list) > 0, "No content files found on server"
        
        log.info("test_get_available_content.found_files",
                count=len(content_list),
                first_few=[c.name for c in content_list[:5]])
        
        # Verify content structure
        for content_file in content_list:
            try:
                assert content_file.name.endswith('.zim'), \
                    f"File {content_file.name} does not end with .zim"
                assert isinstance(content_file.size, int), \
                    f"Size {content_file.size} is not an integer for {content_file.name}"
                assert content_file.size > 0, \
                    f"Size {content_file.size} is not positive for {content_file.name}"
                
                # Verify date format
                try:
                    datetime.strptime(content_file.date, '%Y-%m-%d %H:%M')
                except ValueError as e:
                    raise AssertionError(
                        f"Invalid date format {content_file.date} for {content_file.name}: {e}"
                    )
                
                # Verify English content
                assert any(lang in content_file.name for lang in ['_en_', '_eng_', 'english']), \
                    f"File {content_file.name} does not match English language pattern"
                
                # Verify URL construction
                assert content_file.url.startswith(content_manager.config.base_url), \
                    f"URL {content_file.url} does not start with {content_manager.config.base_url}"
                assert not content_file.url.endswith('/'), \
                    f"URL {content_file.url} ends with /"
                
                log.debug("test_get_available_content.verified_file",
                        name=content_file.name,
                        size=content_file.size,
                        date=content_file.date,
                        url=content_file.url)
                
            except AssertionError as e:
                log.error("test_get_available_content.file_verification_failed",
                        file=content_file,
                        error=str(e))
                raise
                
    except Exception as e:
        log.error("test_get_available_content.failed",
                error=str(e),
                exc_info=True)
        raise

@pytest.mark.asyncio
async def test_download_file(content_manager, tmp_path):
    """Test downloading a small ZIM file."""
    try:
        # First get available content to find the smallest file
        content_list = await content_manager._get_available_content()
        assert len(content_list) > 0, "No content files found on server"
        
        # Find the smallest file by size
        test_file = min(content_list, key=lambda x: x.size)
        assert test_file, "Could not find smallest test file"
        
        log.info("test_download_file.selected_file",
                filename=test_file.name,
                size=test_file.size,
                path=test_file.path,
                url=test_file.url)
        
        # Create test content item
        test_content = ContentItem(
            name=os.path.splitext(test_file.name)[0],
            language="eng",
            category="test",
            description="Test with smallest available file"
        )
        
        dest_path = os.path.join(str(tmp_path), test_file.name)
        log.info("test_download_file.starting",
                url=test_file.url,
                dest_path=dest_path)
        
        success = await content_manager._download_file(
            test_file.url,
            dest_path,
            test_content
        )
        
        assert success, "Download failed"
        assert os.path.exists(dest_path), f"Downloaded file not found at {dest_path}"
        
        file_size = os.path.getsize(dest_path)
        assert file_size > 0, f"Downloaded file is empty (size: {file_size})"
        
        log.info("test_download_file.completed",
                success=success,
                file_exists=os.path.exists(dest_path),
                file_size=file_size)
        
    except Exception as e:
        log.error("test_download_file.failed",
                error=str(e),
                exc_info=True)
        raise

@pytest.mark.asyncio
async def test_update_content(content_manager):
    """Test the complete content update process."""
    # First get available content to find the smallest file
    content_list = await content_manager._get_available_content()
    assert len(content_list) > 0, "No content files found on server"
    
    # Find the smallest file by size
    test_file = min(content_list, key=lambda x: x.size)
    assert test_file, "Could not find smallest test file"
    
    log.info("test_update_content.using_file",
             filename=test_file.name,
             size=test_file.size,
             path=test_file.path)
    
    # Add test content to configuration
    content_manager.config.content_list = [
        ContentItem(
            name=os.path.splitext(test_file.name)[0],
            language="eng",
            category=test_file.path.split('/')[0] if '/' in test_file.path else "test",
            description="Test content"
        )
    ]
    
    # Run update
    await content_manager.update_content()
    
    # Verify state was updated
    content_name = content_manager.config.content_list[0].name
    assert content_name in content_manager.content_state, f"Content {content_name} not found in state"
    state = content_manager.content_state[content_name]
    assert "last_updated" in state
    assert "size" in state
    assert "path" in state
    
    # Verify file was downloaded
    assert os.path.exists(state["path"]), f"Downloaded file not found at {state['path']}"
    assert os.path.getsize(state["path"]) > 0, "Downloaded file is empty"

@pytest.mark.asyncio
async def test_concurrent_downloads(content_manager, tmp_path):
    """Test concurrent download handling."""
    # First get available content to find small files
    content_list = await content_manager._get_available_content()
    assert len(content_list) > 0, "No content files found on server"
    
    # Sort files by size and take the 3 smallest ones
    test_files = sorted(content_list, key=lambda x: x.size)[:3]
    assert len(test_files) >= 3, "Not enough test files found on server"
    
    log.info("test_concurrent_downloads.using_files",
             files=[(f.name, f.size) for f in test_files])
    
    # Create test content items
    test_items = [
        (content_file, ContentItem(
            name=f"test{i}",
            language="eng",
            category=content_file.path.split('/')[0] if '/' in content_file.path else "test",
            description=f"Test content {i}"
        ))
        for i, content_file in enumerate(test_files)
    ]
    
    # Start concurrent downloads
    tasks = []
    for content_file, content in test_items:
        dest_path = os.path.join(str(tmp_path), f"{content.name}.zim")
        task = content_manager._download_file(
            content_file.url,
            dest_path,
            content
        )
        tasks.append(task)
    
    # Wait for all downloads
    results = await asyncio.gather(*tasks)
    
    # Verify results
    assert all(results), "One or more downloads failed"
    assert len(results) == len(test_items), "Not all downloads completed"
    
    # Verify all files were downloaded correctly
    for _, content in test_items:
        path = os.path.join(str(tmp_path), f"{content.name}.zim")
        assert os.path.exists(path), f"Downloaded file not found at {path}"
        assert os.path.getsize(path) > 0, "Downloaded file is empty"
    
    # Verify semaphore worked
    assert content_manager.download_semaphore._value == \
           content_manager.config.options.max_concurrent_downloads

@pytest.mark.asyncio
async def test_cleanup(content_manager, tmp_path):
    """Test cleanup of temporary files."""
    # Create some temporary files
    temp_files = [
        os.path.join(str(tmp_path), f"test{i}.tmp")
        for i in range(3)
    ]
    
    for temp_file in temp_files:
        with open(temp_file, 'w') as f:
            f.write("test")
    
    # Run cleanup
    content_manager.config.data_dir = str(tmp_path)
    await content_manager.cleanup()
    
    # Verify files were removed
    for temp_file in temp_files:
        assert not os.path.exists(temp_file) 