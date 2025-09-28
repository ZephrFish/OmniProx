"""
OmniProx main entry point for python -m omniprox execution
"""

import sys
import os

# Add parent directory to path to ensure imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omniprox.cli import main

if __name__ == '__main__':
    sys.exit(main())