"""
WJX AI Survey Filler - Main Entry Point

Usage:
    python main.py                    # Interactive mode
    python main.py setup              # Setup wizard
    python main.py import-cookies     # Import cookies
    python main.py run                # Run filler
    python main.py interactive        # Interactive menu
"""

import sys
import os

# Add project root to path for src imports
sys.path.insert(0, os.path.dirname(__file__))

from src.cli import main

if __name__ == "__main__":
    main()