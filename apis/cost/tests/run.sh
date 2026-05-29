#!/bin/bash
set -e
cd "$(dirname "$0")/.."
pip3 install -q -r tests/requirements-test.txt
python3 -m pytest tests/ -v --tb=short
