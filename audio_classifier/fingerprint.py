from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class FingerprintResult:
    duration: int
    fingerprint: str


def parse_fpcalc_output(output: str) -> FingerprintResult:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    if not values.get("DURATION") or not values.get("FINGERPRINT"):
        raise ValueError("fpcalc output did not include DURATION and FINGERPRINT")
    return FingerprintResult(duration=int(float(values["DURATION"])), fingerprint=values["FINGERPRINT"])


def run_fpcalc(path: str | Path) -> FingerprintResult:
    proc = subprocess.run(["fpcalc", str(path)], text=True, capture_output=True, check=True)
    return parse_fpcalc_output(proc.stdout)


def fpcalc_available() -> bool:
    return shutil.which("fpcalc") is not None
