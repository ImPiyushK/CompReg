# CompReg installation

## Prerequisites

- Python **3.11+** (3.12 used for the recorded runs)
- At least one C++ compiler: **GCC** (any recent version) or **Clang**.
  CompReg never assumes they exist; `compreg doctor` reports what it finds
  with installation hints. Missing families are reported transparently
  (optional capabilities), never silently skipped.
- Git (needed only for revision bisection)
- CMake/CTest: any system install works. If you have none,
  `pip install cmake ninja` provides working binaries inside the same
  environment (used by `compreg ctest`).

## Linux

```bash
sudo apt-get update && sudo apt-get install -y g++ git   # Debian/Ubuntu
# optional: sudo apt-get install -y clang cmake ninja-build

git clone <your-fork-url> CompReg && cd CompReg
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
compreg doctor
```

Note: on some Debian/Ubuntu setups `python3 -m venv` requires
`sudo apt install python3.12-venv`. If system packages are not installable,
the same tools are obtainable without sudo:

```bash
python3 -m venv --without-pip .venv && \
curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py && \
.venv/bin/python get-pip.py
.venv/bin/pip install -e ".[dev]"
```

## Windows 10

Two supported paths:

**WSL (recommended):** follow the Linux instructions inside WSL (Ubuntu).
Everything below the Windows-specific comments behaves identically.

```powershell
wsl --install            # then enter WSL shell and follow Linux steps
```

**MSYS2 (native Windows):**

1. Install [MSYS2](https://www.msys2.org).
2. In the MSYS2 shell: `pacman -S mingw-w64-ucrt-x86_64-gcc`.
3. Point CompReg at the driver either by config `compiler_paths.gcc` or by
   ensuring `C:\msys64\ucrt64\bin` is on PATH for the Python process.

This is exactly what the windows CI job does (it installs UCRT64 gcc via
`msys2/setup-msys2`, then runs `doctor`, the unit suite, a real
compile-verify subset and `compreg ctest` with the pip-provided cmake/ninja).

The Python orchestration layer is platform-aware (executable suffixes,
quoting via `subprocess.list2cmdline`, venv-aware tool discovery including
pip-installed `cmake`/`ninja` under `%PREFIX%\Scripts`). The curated corpus
uses `printf` formatting that is stable on POSIX/WSL/MSYS2 UCRT; numeric
formatting differences on raw Windows hosts are absorbed by the tolerant
oracles, and exact-string float tests are excluded from the Windows CI
verification subset (see `docs/limitations.md` for the honest boundary).

## Dependency policy

- Runtime dependency of the `compreg` package: **none** (standard library
  only, `tomllib` requires 3.11+).
- Development tools (`requirements-dev.txt`): `pytest`, `cmake`, `ninja`.
- SQLite ships with Python.
- No GPU, cloud, or other paid resources are used at any point.

## Verify the install

```bash
compreg doctor     # compilers, sqlite, cmake/ctest, git, corpus integrity
compreg list-tests # 26 curated tests incl. 2 benchmarks
compreg verify --tests arithmetic_int_basic --opts O2   # first real compile+run
```

If `compreg doctor` reports `sqlite: OK <version>`, persistence is ready; it
stores the database at `artifacts/compreg.db` (configurable).
