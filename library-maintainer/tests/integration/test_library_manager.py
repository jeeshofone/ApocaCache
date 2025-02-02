"""
Integration tests for the library manager.
Tests the library manager's ability to generate and manage library.xml.
"""

import os
import pytest
import xml.etree.ElementTree as ET
import shutil
from datetime import datetime
import asyncio
from pytest_asyncio import fixture as async_fixture

from library_manager import LibraryManager
from config import Config

@async_fixture(scope="function")
async def library_manager(tmp_path):
    """Create a library manager instance for testing."""
    config = Config()
    config.data_dir = str(tmp_path)
    config.library_file = os.path.join(str(tmp_path), "library.xml")
    
    # Copy test ZIM file
    src_zim = os.path.join(
        os.path.dirname(__file__),
        "../fixtures/mock-kiwix-server/content/small.zim"
    )
    dest_zim = os.path.join(str(tmp_path), "small.zim")
    shutil.copy2(src_zim, dest_zim)
    
    manager = LibraryManager(config)
    yield manager
    await manager.cleanup()

@pytest.mark.asyncio
async def test_library_xml_generation(library_manager):
    """Test generating the library.xml file."""
    await library_manager.update_library()
    
    # Verify library.xml exists
    assert os.path.exists(library_manager.config.library_file)
    
    # Parse and verify XML structure
    tree = ET.parse(library_manager.config.library_file)
    root = tree.getroot()
    
    # Check root element
    assert root.tag == "library"
    assert root.get("version") == "20110515"
    
    # Check book elements
    books = root.findall("book")
    assert len(books) > 0
    
    # Verify book metadata
    book = books[0]
    assert book.get("id").startswith("kiwix_")
    assert book.find("title") is not None
    assert book.find("creator") is not None
    assert book.find("publisher") is not None
    assert book.find("date") is not None
    assert book.find("description") is not None
    assert book.find("language") is not None
    assert book.find("size") is not None
    assert book.find("url") is not None
    
    # Verify specific metadata for small.zim
    assert book.find("size").text == "41155"
    assert book.find("language").text == "eng"

@pytest.mark.asyncio
async def test_metadata_extraction(library_manager):
    """Test ZIM file metadata extraction."""
    filepath = os.path.join(
        library_manager.config.data_dir,
        "small.zim"
    )
    metadata = library_manager._get_zim_metadata(filepath)
    
    assert metadata["name"] == "small"
    assert metadata["language"] == "eng"
    assert metadata["creator"] == "small"
    assert metadata["publisher"] == "Kiwix"
    assert "description" in metadata

@pytest.mark.asyncio
async def test_atomic_updates(library_manager):
    """Test atomic library.xml updates."""
    # Create initial library.xml
    await library_manager.update_library()
    initial_mtime = os.path.getmtime(library_manager.config.library_file)
    
    # Small delay to ensure different modification time
    await asyncio.sleep(0.1)
    
    # Update again
    await library_manager.update_library()
    new_mtime = os.path.getmtime(library_manager.config.library_file)
    
    # Verify file was updated
    assert new_mtime > initial_mtime
    
    # Verify no temporary files remain
    temp_file = f"{library_manager.config.library_file}.tmp"
    assert not os.path.exists(temp_file)

@pytest.mark.asyncio
async def test_cleanup(library_manager):
    """Test cleanup of temporary files."""
    # Create a temporary file
    temp_file = f"{library_manager.config.library_file}.tmp"
    with open(temp_file, 'w') as f:
        f.write("test")
    
    # Run cleanup
    await library_manager.cleanup()
    
    # Verify temporary file was removed
    assert not os.path.exists(temp_file) 