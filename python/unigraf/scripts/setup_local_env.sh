#!/bin/bash

# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

usage() {
  cat << EOF
Usage: $(basename "${BASH_SOURCE[0]}") [OPTIONS]

DESCRIPTION:
  Creates a localized Python virtual environment for Unigraf (ChromiumOS)
  development and integration testing.

  The script performs these main actions:
      Determines UTC274 (UTCLibrary) and UCD500 (UniTAP) SDK versions by
      parsing a project Dockerfile or using built-in defaults.

      Sets up a Python virtual environment ('venv') at the specified or
      default installation path (parent directory of this script).
      If a 'venv' exists, it asks to recreate it.

      Downloads the determined SDKs from Google Storage and clones the
      'chromiumos/config' repository (for passport gRPC APIs).

      Installs these SDKs, gRPC APIs, and dependencies from a local
      'requirements.in' file into the virtual environment using pip.

OPTIONS:
  -h, --help          Display this help message and exit.
  --path <dir>        Specify the base installation directory for the
                      environment. Defaults to this script's parent directory.

NOTES:
  - Requires 'python3', 'git', 'wget'.
  - Activate the environment after setup, e.g.:
    source <installation_path>/venv/bin/activate
EOF
  exit 0
}

# Exit immediately if a command exits with a non-zero status.
set -Eeo pipefail

# Trap signals for cleanup.
trap cleanup SIGINT SIGTERM ERR EXIT

# Array to store paths of temporary files to be cleaned up
# Moved here to ensure it's always declared before the trap can be triggered
# by an early error in the script.
declare -a TMP_FILES_TO_CLEANUP


# Determine the installation path.
# This ensures it's an absolute path, even if the script is symlinked.
readonly SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd -P)
INSTALLATION_PATH=$(cd "${SCRIPT_DIR}/.." &>/dev/null && pwd -P)
# Define the path to the requirements.in file.
# This assumes it's in the same parent directory as the script.
readonly REQUIREMENTS_PATH=$(cd "${SCRIPT_DIR}/.." &>/dev/null && pwd -P)

# Define relative path to the Dockerfile for SDK version parsing
readonly DOCKERFILE_RELATIVE_PATH="../../../dockerfiles/Dockerfile"

# Define default SDK version if parsing fails or Dockerfile is missing
readonly DEFAULT_UT274_SDK_VERSION="1.1.11.673"
readonly DEFAULT_UCD500_SDK_VERSION="3.6.350.13545"

# Variables to store parsed SDK versions
UTC274_SDK_VERSION=""
UCD500_SDK_VERSION=""

if [[ -t 2 ]] && [[ "${TERM-}" != "dumb" ]]; then
  NOFORMAT='\033[0m' RED='\033[0;31m' GREEN='\033[0;32m' ORANGE='\033[0;33m'
  BLUE='\033[0;34m' PURPLE='\033[0;35m' CYAN='\033[0;36m' YELLOW='\033[1;33m'
else
  NOFORMAT='' RED='' GREEN='' ORANGE='' BLUE='' PURPLE='' CYAN='' YELLOW=''
fi


cleanup() {
  trap - SIGINT SIGTERM ERR EXIT
  # Clean up temporary files/directories
  if [[ ${#TMP_FILES_TO_CLEANUP[@]} -gt 0 ]]; then
    msg "${YELLOW}Cleaning up temporary files...${NOFORMAT}"
    for file in "${TMP_FILES_TO_CLEANUP[@]}"; do
      if [[ -e "${file}" ]]; then
        rm -rf "${file}"
        msg "Removed: ${file}"
      fi
    done
  fi
}

msg() {
  echo >&2 -e "${1-}"
}

die() {
  local msg_text="$1"
  local exit_code=${2:-1} # Use :- for default value
  msg "${RED}Error: ${msg_text}${NOFORMAT}"
  exit "${exit_code}"
}

# Prompt for user confirmation.
confirm_action() {
  local prompt_message="$1"
  read -rp "${prompt_message} (y/N):" confirmation

  if [[ "${confirmation}" =~ ^[yY]$ ]]; then
    return 0 # Confirmed
  else
    return 1 # Not confirmed
  fi
}

# Parses an SDK version from a Dockerfile.
# Args:
#   $1: Path to the Dockerfile.
#   $2: The ARG name to look for (e.g., "UTC274_SDK_VERSION").
#   $3: The default version to return if not found.
# Returns: The parsed version string or the default version.
parse_sdk_version_from_dockerfile() {
  local dockerfile_path="$1"
  local arg_name="$2"
  local default_version="$3"
  local version=""

  if [[ -f "${dockerfile_path}" ]]; then
    # Use grep with Perl-compatible regular expressions (-P)
    # and -o to print only the matched part. \K resets match start.
    version=$(grep -oP "^ARG ${arg_name}=\\K[^\\s]+" "${dockerfile_path}" | head -n 1)
  fi

  if [[ -z "${version}" ]]; then
    msg "${ORANGE}Warning: Could not find '${arg_name}' in '${dockerfile_path}' or Dockerfile is missing. Using default: ${default_version}${NOFORMAT}"
    echo "${default_version}"
  else
    echo "${version}"
  fi
}

create_env() {
  local env_path="$1"
  local utc274_sdk_version="$2"
  local ucd500_sdk_version="$3"
  local venv_path="${env_path}/venv"
  local tmp_download_dir
  tmp_download_dir=$(mktemp -d -t sdk_downloads_XXXXXX) # Create a unique temp dir

  # Add the temporary download directory to the cleanup list
  TMP_FILES_TO_CLEANUP+=("${tmp_download_dir}")

  # Check if the base environment path already exists
  if [[ -d "${env_path}" ]]; then
    msg "${ORANGE}Warning: Base environment path '${env_path}' already exists.${NOFORMAT}"
  else
    msg "${GREEN}Creating base environment directory: ${env_path}${NOFORMAT}"
    mkdir -p "${env_path}" || die "Failed to create base directory: ${env_path}"
  fi

  # Check for the Python virtual environment (venv)
  if [[ -d "${venv_path}" ]]; then
    if confirm_action "Do you want to delete and recreate it?"; then
      msg "${YELLOW}Deleting existing virtual environment: ${venv_path}${NOFORMAT}"
      rm -rf "${venv_path}" || die "Failed to delete existing virtual environment at '${venv_path}'."
      msg "${GREEN}Existing virtual environment deleted.${NOFORMAT}"
      # Fall through to creation logic
    else
      die "User chose not to recreate the virtual environment. Aborting."
    fi
  fi

  msg "${GREEN}Creating Python virtual environment at: ${venv_path}${NOFORMAT}"
  if ! command -v python3 &> /dev/null; then
      die "python3 is not installed or not in PATH. Cannot create virtual environment."
  fi

  python3 -m venv "${venv_path}" || die "Failed to create Python virtual environment at '${venv_path}'."
  msg "${GREEN}Python virtual environment created successfully!${NOFORMAT}"

  # --- Download SDK Files ---
  msg "${GREEN}Downloading SDK files and API repositories...${NOFORMAT}"

  local utc274_url="https://storage.googleapis.com/chromeos-localmirror/distfiles/UTCLibrary-${utc274_sdk_version}.tar.gz"
  local ucd500_url="https://storage.googleapis.com/chromeos-localmirror/distfiles/UniTAP-${ucd500_sdk_version}.tar.gz"
  local api_repo_url="https://chromium.googlesource.com/chromiumos/config"

  local utc274_filename="UTCLibrary-${utc274_sdk_version}.tar.gz"
  local ucd500_filename="UniTAP-${ucd500_sdk_version}.tar.gz"
  local api_repo_dir="${tmp_download_dir}/config"


  local utc274_download_path="${tmp_download_dir}/${utc274_filename}"
  local ucd500_download_path="${tmp_download_dir}/${ucd500_filename}"

  msg "Downloading ${utc274_filename}..."
  wget -q --show-progress "${utc274_url}" -O "${utc274_download_path}" || die "Failed to download ${utc274_filename} from ${utc274_url}"

  msg "Downloading ${ucd500_filename}..."
  wget -q --show-progress "${ucd500_url}" -O "${ucd500_download_path}" || die "Failed to download ${ucd500_filename} from ${ucd500_url}"

  msg "Cloning passport gRPC APIs from ${api_repo_url}..."
  git clone "${api_repo_url}" "${api_repo_dir}" || die "Failed to clone API repository from ${api_repo_url}"

  msg "${GREEN}Files downloaded and repositories cloned to ${tmp_download_dir}.${NOFORMAT}"

  # --- Pip Install Dependencies ---
  msg "${GREEN}Installing SDKs and other dependencies into virtual environment...${NOFORMAT}"
  local pip_path="${venv_path}/bin/pip"

  if [[ ! -f "${pip_path}" ]]; then
      die "pip executable not found in virtual environment at ${pip_path}. Virtual environment might be corrupted."
  fi

  msg "Installing downloaded SDK archives..."
  "${pip_path}" install "${utc274_download_path}" "${ucd500_download_path}" || die "Failed to pip install SDK files."

  msg "Installing passport gRPC APIs..."
  "${pip_path}" install "${api_repo_dir}/python" || die "Failed to install passport gRPC APIs."

  if [[ -f "${REQUIREMENTS_PATH}/requirements.in" ]]; then
    msg "Installing dependencies from requirements.in..."
    # Filter for lines with '==' (pinned versions) and install them
    cat "${REQUIREMENTS_PATH}/requirements.in" | \
      grep -E '^[[:space:]]*[^#[:space:]]+==.*$' | \
      xargs -L 1 "${pip_path}" install || die "Failed to install dependencies from requirements.in."
  else
    msg "${ORANGE}Warning: requirements.in not found at ${REQUIREMENTS_PATH}/requirements.in. Skipping additional dependency installation.${NOFORMAT}"
  fi

  msg "${GREEN}SDKs and dependencies installed successfully!${NOFORMAT}"
}

main() {
  # Parse command-line arguments.
  while [[ $# -gt 0 ]]; do
    case "${1}" in
      -h | --help)
        usage
        ;;
      --path)
        if [[ -n "${2-}" ]]; then # Check if next argument exists
          INSTALLATION_PATH="$2"
          shift # Consume the argument value
        else
          die "--path requires an argument."
        fi
        ;;
      -?*)
        die "Unknown option: $1"
        ;;
      *)
        # Treat any remaining argument as an error for this script's usage
        die "Unexpected argument: '$1'. See --help for usage."
        ;;
    esac
    shift # Consume the current argument
  done

  # Validate the installation path (optional but recommended)
  if [[ -z "${INSTALLATION_PATH}" ]]; then
    die "Installation path cannot be empty. Use --path or ensure default is set."
  fi

  local dockerfile_full_path="${SCRIPT_DIR}/${DOCKERFILE_RELATIVE_PATH}"
  UTC274_SDK_VERSION=$(parse_sdk_version_from_dockerfile "${dockerfile_full_path}" "UTC274_SDK_VERSION" "${DEFAULT_UT274_SDK_VERSION}")
  UCD500_SDK_VERSION=$(parse_sdk_version_from_dockerfile "${dockerfile_full_path}" "UCD500_SDK_VERSION" "${DEFAULT_UCD500_SDK_VERSION}")

  msg "Parsed SDK Versions:"
  msg "  UTC274_SDK_VERSION: ${CYAN}${UTC274_SDK_VERSION}${NOFORMAT}"
  msg "  UCD500_SDK_VERSION: ${CYAN}${UCD500_SDK_VERSION}${NOFORMAT}"

  msg "Installation path is set to: ${CYAN}${INSTALLATION_PATH}${NOFORMAT}"

  # Prompt for confirmation before proceeding, mentioning the venv and SDKs.
  if confirm_action "Are you sure you want to proceed with creating/updating the environment in '${INSTALLATION_PATH}'?"; then
    # Pass the SDK versions to create_env
    create_env "${INSTALLATION_PATH}" "${UTC274_SDK_VERSION}" "${UCD500_SDK_VERSION}"
  else
    die "User aborted script execution."
  fi

  msg "${GREEN}Script finished successfully!${NOFORMAT}"
  exit 0
}

# Run the main function with all arguments.
main "$@"
