"""`python -m stocktake`, for when the console script is not on the path."""

import sys

from stocktake.cli import main

if __name__ == "__main__":
    sys.exit(main())
