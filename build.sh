#!/bin/bash
set -e
cd "$(dirname "$0")"
rm -rf dist/ build/
pipx run build --sdist
echo "Built: $(ls dist/*.tar.gz)"
