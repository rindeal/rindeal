#!/bin/bash

set -eu

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

RENDERER="${SCRIPT_DIR}/README.md-renderer.py"

TEMPLATE_PATH="${SCRIPT_DIR}/README.md.jinja2"
OUTPUT_PATH="${SCRIPT_DIR}/README.md"

"${RENDERER}" < "${TEMPLATE_PATH}" > "${OUTPUT_PATH}"

echo "Template rendered successfully."
