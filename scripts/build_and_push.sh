#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="joafri/map-poster-studio"
TAG="latest"

docker build -t "${IMAGE_NAME}:${TAG}" .
docker push "${IMAGE_NAME}:${TAG}"
