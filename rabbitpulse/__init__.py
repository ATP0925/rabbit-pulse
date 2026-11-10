"""
RabbitPulse: Lightweight, adaptive background sentinel for CodeRabbit reviews and GitHub issues.
"""

import sys

# Ensure cross-platform UTF-8 encoding support
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

__version__ = "1.0.0"
__author__ = "ATP0925"
__license__ = "MIT"
