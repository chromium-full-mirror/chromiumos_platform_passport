#!/bin/bash
# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

REMOTE_SOURCE=false
PUSH=false
PLATFORMS="linux/amd64"
TAG="${USER}-testing" # Default primary tag
AR_REGION="us"
PROJECT_ID="cros-passport"
AR_REPOSITORY="passport"
IMAGE_NAME="passport"
SHORT_SHA="local"
BRANCH_NAME="unknown"

usage() {
  echo "Usage: $0 [options]"
  echo "  --remote_source        Use remote Git URLs for build contexts."
  echo "  --push                 Push the built image to Artifact Registry."
  echo "  --platforms <list>     Comma-separated list of platforms (default: ${PLATFORMS})."
  echo "  --tag <tag>            Primary image tag (default: ${TAG})."
  echo "  --ar_region <region>   Artifact Registry region (default: ${AR_REGION})."
  echo "  --project_id <id>      GCP Project ID (default: ${PROJECT_ID})."
  echo "  --ar_repository <repo> Artifact Registry repository (default: ${AR_REPOSITORY})."
  echo "  --image_name <name>    Docker image name (default: ${IMAGE_NAME})."
  echo "  --short_sha <sha>      Commit SHA for tagging (default: ${SHORT_SHA})."
  echo "  --branch_name <branch> Git branch name (default: ${BRANCH_NAME})."
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote_source) REMOTE_SOURCE=true; shift ;;
    --push) PUSH=true; shift ;;
    --platforms) PLATFORMS="$2"; shift 2 ;;
    --platforms=*) PLATFORMS="${1#*=}"; shift ;;
    --tag) TAG="$2"; shift 2 ;;
    --tag=*) TAG="${1#*=}"; shift ;;
    --ar_region) AR_REGION="$2"; shift 2 ;;
    --ar_region=*) AR_REGION="${1#*=}"; shift ;;
    --project_id) PROJECT_ID="$2"; shift 2 ;;
    --project_id=*) PROJECT_ID="${1#*=}"; shift ;;
    --ar_repository) AR_REPOSITORY="$2"; shift 2 ;;
    --ar_repository=*) AR_REPOSITORY="${1#*=}"; shift ;;
    --image_name) IMAGE_NAME="$2"; shift 2 ;;
    --image_name=*) IMAGE_NAME="${1#*=}"; shift ;;
    --short_sha) SHORT_SHA="$2"; shift 2 ;;
    --short_sha=*) SHORT_SHA="${1#*=}"; shift ;;
    --branch_name) BRANCH_NAME="$2"; shift 2 ;;
    --branch_name=*) BRANCH_NAME="${1#*=}"; shift ;;
    --help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

# Exit immediately if a command exits with a non-zero status.
set -euo pipefail

TEMP_DIR="/tmp/passport_docker"
DIR="$(dirname "$(realpath -e "${BASH_SOURCE[0]}")")"
DOCKERFILE="${DIR}/../dockerfiles/Dockerfile"

# Remote Git repositories for build context.
REMOTE_APICONFIG_URL="https://chromium.googlesource.com/chromiumos/config.git#main"
REMOTE_PASSPORT_URL="https://chromium.googlesource.com/chromiumos/platform/passport.git#main"
REMOTE_DEV_URL="https://chromium.googlesource.com/chromiumos/platform/dev-util.git#main:src"

# Variables to hold the commit SHAs.
FLAGS="-f ${DOCKERFILE}"
APICONFIG_COMMIT=""
PASSPORT_COMMIT=""
PASSPORT_BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Temporarily disable exit-on-error to gracefully handle git failures.
set +e

# If local build use local checkout, otherwise use checked in files (default).
if [[ "${REMOTE_SOURCE}" == true ]]; then
    echo "Using remote sources for build context..."
    FLAGS+="
        --build-context apiconfig=${REMOTE_APICONFIG_URL}
        --build-context passport=${REMOTE_PASSPORT_URL}
        --build-context dev=${REMOTE_DEV_URL}
        "
    # Strip '#main' from URL, get latest commit, and suppress errors.
    APICONFIG_COMMIT=$(git ls-remote "${REMOTE_APICONFIG_URL%#*}" refs/heads/main 2>/dev/null | cut -f1)
    PASSPORT_COMMIT=$(git ls-remote "${REMOTE_PASSPORT_URL%#*}" refs/heads/main 2>/dev/null | cut -f1)
else
    echo "Using local sources for build context..."
    FLAGS+="
        --build-context apiconfig=${DIR}/../../../config/
        --build-context passport=${DIR}/..
        --build-context dev=${DIR}/../../dev/src
        "
    # Get the current commit SHA from local repos and suppress errors.
    APICONFIG_COMMIT=$( (git -C "${DIR}/../../../config/" rev-parse HEAD) 2>/dev/null )
    PASSPORT_COMMIT=$( (git -C "${DIR}/.." rev-parse HEAD) 2>/dev/null )
fi

# Re-enable exit-on-error for the rest of the script.
set -e

echo "Using apiconfig commit string: APICONFIG_COMMIT:${APICONFIG_COMMIT:-unknown}"
echo "Using passport commit string: PASSPORT_COMMIT:${PASSPORT_COMMIT:-unknown}"

# Add commit messages as build arguments for the Dockerfile.
FLAGS+=" --build-arg APICONFIG_COMMIT=APICONFIG_COMMIT:${APICONFIG_COMMIT:-unknown}"
FLAGS+=" --build-arg PASSPORT_COMMIT=PASSPORT_COMMIT:${PASSPORT_COMMIT:-unknown}"
FLAGS+=" --build-arg PASSPORT_BUILD_DATE=PASSPORT_BUILD_DATE:${PASSPORT_BUILD_DATE:-unknown}"

IMAGE_BASE="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPOSITORY}/${IMAGE_NAME}"

if [[ "${PUSH}" == true ]]; then
    echo "Starting multi-platform build and push to ${IMAGE_BASE} for platforms: ${PLATFORMS}..."
    docker buildx rm passport-builder || true
    docker buildx create --use --name passport-builder

    BUILD_TAGS=("-t" "${IMAGE_BASE}:${TAG}")
    if [[ -n "${SHORT_SHA}" && "${SHORT_SHA}" != "local" ]]; then
        # Additional tag with the provided SHA (if any).
        BUILD_TAGS+=("-t" "${IMAGE_BASE}:${SHORT_SHA}")
    fi
    echo "Applying tags: ${BUILD_TAGS[@]}"

    docker buildx build \
        --platform="${PLATFORMS}" \
        --cache-from "type=registry,ref=${IMAGE_BASE}:buildcache-${TAG}" \
        --cache-to "type=registry,ref=${IMAGE_BASE}:buildcache-${TAG},mode=max" \
        "${BUILD_TAGS[@]}" \
        ${FLAGS} \
        --push \
        "${DIR}/."
else
    echo "Local build only for platforms: ${PLATFORMS}. Images will be saved as .tar archives in ${TEMP_DIR}."
    mkdir -p "${TEMP_DIR}"
    IFS=',' read -ra PLATFORM_ARRAY <<< "${PLATFORMS}"
    for PLATFORM in "${PLATFORM_ARRAY[@]}"; do
        echo "Building for platform: ${PLATFORM}..."

        PLATFORM_SUFFIX=$(echo "${PLATFORM}" | tr '/' '-')
        LOCAL_TAG="${IMAGE_BASE}:${TAG}-local-${PLATFORM_SUFFIX}"
        docker buildx build \
            --platform="${PLATFORM}" \
            -t "${LOCAL_TAG}" \
            --output type=docker \
            ${FLAGS} \
            "${DIR}/."

        TAR_FILE="${TEMP_DIR}/passport-${PLATFORM_SUFFIX}.tar"
        echo "Saving ${LOCAL_TAG} to ${TAR_FILE}"
        docker save -o "${TAR_FILE}" "${LOCAL_TAG}"
    done
fi

echo "Script finished."
