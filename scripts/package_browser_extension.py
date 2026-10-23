"""Build the exact same ZIP served by the Lucas extension download endpoint."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpt_windows_connector.browser_extension_archive import extension_archive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(extension_archive())
    print(args.output.resolve())


if __name__ == "__main__":
    main()
