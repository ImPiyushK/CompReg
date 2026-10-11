"""Clang adapter."""

from __future__ import annotations

from typing import ClassVar, Tuple

from .base import CompilerAdapter, CompilerIdentityData


class ClangAdapter(CompilerAdapter):
    family: ClassVar[str] = "clang"
    cpp_candidates: ClassVar[Tuple[str, ...]] = (
        "clang++",
        "clang++-18",
        "clang++-17",
        "clang++-16",
        "clang++-15",
    )
    version_regex: ClassVar[str] = r"(?:clang|LLVM) version (\d+)\.(\d+)\.(\d+)"

    def query_identity(self) -> CompilerIdentityData:
        version_text = self.capture_version_text()
        major, minor, patch = self.parse_version(version_text)
        return CompilerIdentityData(
            family=self.family,
            executable=self.executable,
            version_text=version_text,
            version_major=major,
            version_minor=minor,
            version_patch=patch,
            target=self.query_target(),
        )
