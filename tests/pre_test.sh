#!/bin/sh
# pre-test procedure specific for VITO Jenkins CI toolchain
# executed just before running the tests

set -eux
pwd

# Root folder for temp folders during tests (e.g. through `tmp_path` fixture).
# Assigned to `PYTEST_DEBUG_TEMPROOT` from Jenkinsfile.
mkdir -p pytest-tmp
chown jenkins pytest-tmp
