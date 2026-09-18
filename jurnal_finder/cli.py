#!/usr/bin/env python3
"""CLI wrapper untuk jurnal_finder.

Bisa dipanggil sebagai: jurnal-finder atau jf
"""


def main():
    from jurnal_finder.core import main as core_main
    try:
        core_main()
    except (KeyboardInterrupt, EOFError):
        print("\n\n👋 Dibatalkan. Sampai jumpa!\n")


if __name__ == "__main__":
    main()