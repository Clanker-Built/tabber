"""Entry point for python -m tabber."""

import sys


def main():
    from tabber.application import TabberApplication
    app = TabberApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
