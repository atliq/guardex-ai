# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""Constants shared by the SDK surface and the in-process engine.

Dependency-free so ``_engine`` can import it without depending on the
SDK layer above it.
"""

# 0.85 keeps real-PII recall near 100% while excluding the 0.6-0.8
# false-positive band where short conversational tokens land.
DEFAULT_PII_THRESHOLD: float = 0.85
