#!/usr/bin/env python3
"""Freeze run.py into desktop/build/server/ (PyInstaller, one-dir) for the Electron shell.

Run it from anywhere, on the OS you are building for (PyInstaller does not cross-compile):

    pip install -r requirements-desktop.txt
    python desktop/build_server.py            # add --dry-run to just print the command
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # the project folder that holds run.py and mailweb/
BUILD = HERE / "build"
NAME = "mailweb-server"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print the PyInstaller command and stop")
    args = parser.parse_args()

    static = ROOT / "mailweb" / "web" / "static"
    if not (ROOT / "run.py").is_file() or not static.is_dir():
        print(f"expected run.py and mailweb/web/static in {ROOT}", file=sys.stderr)
        return 1

    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console",
        "--name", NAME,
        "--paths", str(ROOT),
        "--distpath", str(BUILD / "dist"), "--workpath", str(BUILD / "work"), "--specpath", str(BUILD / "work"),
        # run.py finds the front-end at <bundle>/mailweb/web/static (see HERE in run.py)
        "--add-data", f"{static}{os.pathsep}mailweb/web/static",
        "--collect-submodules", "mailweb",
        "--exclude-module", "tkinter",
        str(ROOT / "run.py"),
    ]
    print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
    if args.dry_run:
        return 0

    shutil.rmtree(BUILD, ignore_errors=True)
    subprocess.run(cmd, check=True, cwd=ROOT)
    shutil.move(str(BUILD / "dist" / NAME), str(BUILD / "server"))
    shutil.rmtree(BUILD / "dist", ignore_errors=True)
    shutil.rmtree(BUILD / "work", ignore_errors=True)

    exe = BUILD / "server" / (NAME + (".exe" if os.name == "nt" else ""))
    print(f"\nsmoke test: {exe} --help")
    subprocess.run([str(exe), "--help"], check=True, stdout=subprocess.DEVNULL)
    print(f"ok: {exe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
