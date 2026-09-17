#!/usr/bin/env python3
"""
CLI wrapper untuk jurnal_finder.
Bisa dipanggil sebagai: jurnal-finder atau jf
"""

import sys
import os

# Pastikan working directory adalah tempat script dijalankan
# (untuk menemukan downloads/ folder)
def ensure_cwd():
    """Set working directory ke tempat user menjalankan command."""
    # Gunakan directory saat ini, bukan tempat script berada
    pass

def main():
    ensure_cwd()
    # Import core modul
    from jurnal_finder.core import main as core_main
    core_main()

if __name__ == "__main__":
    main()
