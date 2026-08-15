"""Entry point for BlueP."""

import sys

from bluep.app import BluePApp


def main() -> int:
    """Launch the BlueP IDE."""
    app = BluePApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
