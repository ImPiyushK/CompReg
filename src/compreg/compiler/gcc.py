"""GCC adapter."""

from __future__ import annotations

from typing import ClassVar, Tuple

from .base import CompilerAdapter, CompilerIdentityData


class GccAdapter(CompilerAdapter):
    family: ClassVar[str] = "gcc"
    cpp_candidates: ClassVar[Tuple[str, ...]] = (
        "g++",
        "c++",
        "g++-14",
        "g++-13",
        "g++-12",
        "g++-11",
    )
    version_regex: ClassVar[str] = r"version\s+(\d+)\.(\d+)(?:\.(\d+))?"

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
