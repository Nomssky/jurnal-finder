#!/usr/bin/env python3
"""CLI wrapper untuk jurnal_finder.

Bisa dipanggil sebagai: jurnal-finder atau jf
"""


def main():
    from jurnal_finder.core import main as core_main
    core_main()


if __name__ == "__main__":
    main()