import sys
import os

# Prepend overlay path to ensure it overrides upstream imports
overlay_path = os.path.join(os.path.dirname(__file__), "lidarrmetadata")
sys.path.insert(0, overlay_path)

# Then import the upstream server entrypoint
from lidarrmetadata.server import main

if __name__ == "__main__":
    sys.exit(main())
