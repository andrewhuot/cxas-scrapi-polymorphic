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

"""Shared instruction-text helpers for the Polymorphism Engine.

Both the compiler (``poly.engine``) and the adapter validators
(``poly.validators``) need to reason about XML-style ``<section>`` blocks in
agent instructions in exactly the same way.  Keeping the matcher here — rather
than duplicating it in each module — guarantees that ``cxas poly validate`` and
``cxas poly build`` agree: a card that validates clean always compiles, and a
card that fails to compile is always reported by validation first.

Pure functions, no I/O, depends only on :mod:`poly.models`.
"""

import re
from functools import lru_cache
from typing import Pattern

from cxas_scrapi.poly.models import InstructionDiff


@lru_cache(maxsize=256)
def section_regex(tag: str) -> Pattern[str]:
    """Return the compiled regex that matches a ``<tag ...>...</tag>`` block.

    Attributes on the opening tag are allowed; a matching closing tag is
    required.  The match is non-greedy and spans newlines.
    """
    return re.compile(
        rf"<{re.escape(tag)}\b[^>]*>.*?</{re.escape(tag)}>",
        re.DOTALL,
    )


def has_section(text: str, tag: str) -> bool:
    """True if ``text`` contains a complete ``<tag>...</tag>`` block."""
    if not tag:
        return False
    return bool(section_regex(tag).search(text))


def apply_instruction_diff(text: str, diff: InstructionDiff) -> str:
    """Apply one :class:`InstructionDiff` to ``text`` and return the result.

    Raises:
        ValueError: if ``mode == "replace_section"`` and either ``sectionTag``
            is missing or the section is not present in ``text``.  The message
            is prefixed with ``AD003`` so callers can surface it consistently.
    """
    if diff.mode == "append":
        sep = "" if text.endswith("\n") else "\n"
        return f"{text}{sep}\n{diff.content}"
    if diff.mode == "prepend":
        return f"{diff.content}\n\n{text}"

    # replace_section
    tag = diff.section_tag
    if not tag:
        raise ValueError(
            f"AD003: replace_section requires sectionTag (agent "
            f"'{diff.agent}')."
        )
    pattern = section_regex(tag)
    if not pattern.search(text):
        raise ValueError(
            f"AD003: section <{tag}> not found in instruction for agent "
            f"'{diff.agent}'."
        )
    replacement = f"<{tag}>\n{diff.content.rstrip()}\n</{tag}>"
    return pattern.sub(lambda _m: replacement, text, count=1)
