"""CompReg - Automated Compiler Verification & Regression Analysis.

A CPU-only framework for differential compiler testing, benchmarking,
historical regression tracking and failure triage.

The framework covers standard desktop toolchains (GCC/Clang building C++17
for a host CPU). It does not verify NVIDIA internal compilers, CUDA, or GPU
instruction semantics.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
