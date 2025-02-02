#!/bin/bash

# Get current user's UID and GID
CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)

# Create kiwix directory if it doesn't exist
mkdir -p examples/kiwix

# Create content_state.json with proper permissions
touch examples/kiwix/content_state.json
touch examples/kiwix/library.xml

# Set ownership and permissions
chown -R $CURRENT_UID:$CURRENT_GID examples/kiwix
chmod -R 755 examples/kiwix
chmod 644 examples/kiwix/library.xml
chmod 644 examples/kiwix/content_state.json

echo "Kiwix directory setup complete with UID:$CURRENT_UID GID:$CURRENT_GID" 