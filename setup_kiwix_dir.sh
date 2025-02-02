#!/bin/bash

# Create kiwix directory if it doesn't exist
mkdir -p examples/kiwix

# Set permissions
chmod 755 examples/kiwix

# Create empty library.xml if it doesn't exist
touch examples/kiwix/library.xml
chmod 644 examples/kiwix/library.xml

echo "Kiwix directory setup complete" 