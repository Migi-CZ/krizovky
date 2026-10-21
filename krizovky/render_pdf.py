"""SVG -> PDF through headless LibreOffice (``soffice``)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class PdfError(RuntimeError):
    """The PDF could not be produced."""


def soffice_path() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def to_pdf(svg_path: Path, out_dir: Path | None = None, *, timeout: float = 120.0) -> Path:
    svg_path = Path(svg_path)
    if not svg_path.is_file():
        raise PdfError(f"SVG not found: {svg_path}")
    soffice = soffice_path()
    if soffice is None:
        raise PdfError("LibreOffice (soffice) not found on PATH; install it or skip the PDF step")
    out_dir = Path(out_dir) if out_dir is not None else svg_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / (svg_path.stem + ".pdf")
    # Remove a stale PDF, otherwise a silent failure would look like success.
    pdf.unlink(missing_ok=True)
    cmd = [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(svg_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise PdfError(f"soffice timed out after {timeout:.0f} s converting {svg_path}") from exc
    except OSError as exc:
        raise PdfError(f"cannot run {soffice}: {exc}") from exc
    if proc.returncode != 0:
        raise PdfError(f"soffice exited with {proc.returncode}: {(proc.stderr or proc.stdout).strip()}")
    if not pdf.is_file():
        # A running LibreOffice GUI (same user profile) can make headless
        # conversion exit 0 without writing anything.
        raise PdfError(f"soffice produced no {pdf.name}; if a LibreOffice window is open, "
                       f"close it and retry. Output: {(proc.stdout + proc.stderr).strip()}")
    return pdf
