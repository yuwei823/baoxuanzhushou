"""Project CLI; register operational commands only when implemented."""

import argparse

from insurance_audit import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="insurance-audit",
        description="Insurance audit project. Operational commands are not implemented yet.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.parse_args()
    parser.print_help()


if __name__ == "__main__":
    main()
