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

from content_manager import ContentManager
from config import Config, ContentItem

@async_fixture(scope="function")
async def content_manager():
    """Create a content manager instance for testing."""
    config = Config()
    # Override the base URL to point to our mock server
    config.base_url = "http://mock-kiwix-server/"
    manager = ContentManager(config)
    yield manager
    await manager.cleanup()

@pytest.mark.asyncio
async def test_get_available_content(content_manager):
    """Test fetching available content from mock server."""
    content_list = await content_manager._get_available_content()
    assert len(content_list) > 0
    
    # Verify content structure
    for filename, date_str, size in content_list:
        assert filename.endswith('.zim')
        assert isinstance(size, int)
        # Verify date format
        datetime.strptime(date_str, '%Y-%m-%d %H:%M')

@pytest.mark.asyncio
async def test_download_file(content_manager, tmp_path):
    """Test downloading a ZIM file."""
    test_content = ContentItem(
        name="small",
        language="eng",
        category="test",
        description="Test content"
    )
    
    dest_path = os.path.join(str(tmp_path), "small.zim")
    success = await content_manager._download_file(
        "small.zim",
        dest_path,
        test_content
    )
    
    assert success
    assert os.path.exists(dest_path)
    assert os.path.getsize(dest_path) == 41155  # Size of small.zim

@pytest.mark.asyncio
async def test_update_content(content_manager):
    """Test the complete content update process."""
    # Add test content to configuration
    content_manager.config.content_list = [
        ContentItem(
            name="small",
            language="eng",
            category="test",
            description="Test content"
        )
    ]
    
    # Run update
    await content_manager.update_content()
    
    # Verify state was updated
    assert "small" in content_manager.content_state
    state = content_manager.content_state["small"]
    assert "last_updated" in state
    assert "size" in state
    assert "path" in state
    
    # Verify file was downloaded
    assert os.path.exists(state["path"])
    assert os.path.getsize(state["path"]) == 41155

@pytest.mark.asyncio
async def test_concurrent_downloads(content_manager, tmp_path):
    """Test concurrent download handling."""
    test_files = [
        ("small.zim", ContentItem("test1", "eng", "test")),
        ("small.zim", ContentItem("test2", "eng", "test")),
        ("small.zim", ContentItem("test3", "eng", "test"))
    ]
    
    # Start concurrent downloads
    tasks = []
    for filename, content in test_files:
        dest_path = os.path.join(str(tmp_path), f"{content.name}.zim")
        task = content_manager._download_file(
            filename,
            dest_path,
            content
        )
        tasks.append(task)
    
    # Wait for all downloads
    results = await asyncio.gather(*tasks)
    
    # Verify results
    assert all(results)
    assert len(results) == len(test_files)
    
    # Verify all files were downloaded correctly
    for _, content in test_files:
        path = os.path.join(str(tmp_path), f"{content.name}.zim")
        assert os.path.exists(path)
        assert os.path.getsize(path) == 41155
    
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