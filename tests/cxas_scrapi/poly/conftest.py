# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared fixtures for polymorphism engine tests."""

import shutil
from pathlib import Path

import pytest

# tests/cxas_scrapi/poly/conftest.py -> tests/
_TESTS_ROOT = Path(__file__).resolve().parents[2]
_BASE_FIXTURE = _TESTS_ROOT / "testdata" / "poly" / "base"


@pytest.fixture
def base_dir() -> Path:
    """Path to the committed minimal poly base project fixture."""
    return _BASE_FIXTURE


@pytest.fixture
def copied_base(tmp_path: Path) -> Path:
    """A writable copy of the base fixture under ``tmp_path``."""
    dest = tmp_path / "base"
    shutil.copytree(_BASE_FIXTURE, dest)
    return dest
