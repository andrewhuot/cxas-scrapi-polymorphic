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

# tests/cxas_scrapi/poly/conftest.py -> tests/ -> repo root
_TESTS_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _TESTS_ROOT.parent
_BASE_FIXTURE = _TESTS_ROOT / "testdata" / "poly" / "base"
_BELLA_NOTTE = _REPO_ROOT / "examples" / "bella_notte"
_POLYMORPHIC_PIZZA = _REPO_ROOT / "examples" / "polymorphic_pizza"


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


@pytest.fixture
def bella_notte_dir() -> Path:
    """Path to the real Bella Notte example project (a lint-clean base)."""
    if not (_BELLA_NOTTE / "app.json").exists():
        pytest.skip("examples/bella_notte not available")
    return _BELLA_NOTTE


@pytest.fixture
def polymorphic_pizza_dir() -> Path:
    """Path to the Polymorphic Pizza product-demo project."""
    if not (_POLYMORPHIC_PIZZA / "app.json").exists():
        pytest.skip("examples/polymorphic_pizza not available")
    return _POLYMORPHIC_PIZZA


@pytest.fixture
def copied_pizza_with_identity(
    tmp_path: Path, polymorphic_pizza_dir: Path
) -> Path:
    """Pizza demo copy whose chat adapter sets an explicit appIdentity."""
    dst = tmp_path / "pizza"
    shutil.copytree(polymorphic_pizza_dir, dst)
    card = dst / "adapters" / "chat.adapter.yaml"
    card.write_text(
        card.read_text()
        + "\nappIdentity:\n  displayName: Override Chat Name\n"
    )
    return dst
