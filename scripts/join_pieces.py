#!/usr/bin/env python3
"""Rebuild an inbox upload from its pieces.

Usage: join_pieces.py OUT_FILE PIECE [PIECE ...]   (pieces in the order listed in the job's `chunks`)
Each piece is a 0x00 header byte followed by a slice of the original file.
"""
import sys

out, pieces = sys.argv[1], sys.argv[2:]
with open(out, "wb") as dst:
    for path in pieces:
        with open(path, "rb") as src:
            if src.read(1) != b"\x00":
                sys.exit(f"{path}: missing piece header")
            while chunk := src.read(1 << 20):
                dst.write(chunk)
