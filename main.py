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

# Add src to path
sys.path.insert(0, __file__.rsplit('/', 1)[0] + '/src')

from cli import main

if __name__ == "__main__":
    main()