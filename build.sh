#!/bin/bash
set -e
cd "$(dirname "$0")"
rm -rf dist/ build/
pipx run build --sdist
cd dist && ln -sf sweatpants-[0-9]*.tar.gz sweatpants-latest.tar.gz && cd ..
echo "Built: $(ls dist/*.tar.gz)"
