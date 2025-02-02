#!/bin/bash
set -e

# Configuration
IMAGE_NAME="apocacache/library-maintainer"
PLATFORMS="linux/amd64,linux/arm64"
VERSION=$(git describe --tags --always --dirty)

# Enable Docker BuildKit
export DOCKER_BUILDKIT=1

# Create and use buildx builder
docker buildx create --use

# Build and push multi-architecture image
echo "Building ${IMAGE_NAME}:${VERSION} for platforms: ${PLATFORMS}"
docker buildx build \
  --platform ${PLATFORMS} \
  --tag ${IMAGE_NAME}:${VERSION} \
  --tag ${IMAGE_NAME}:latest \
  --file Dockerfile \
  --push \
  .

echo "Build complete for ${IMAGE_NAME}:${VERSION}" 