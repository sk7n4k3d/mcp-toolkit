#!/usr/bin/env python3
"""MCP CAD — modelling (OpenSCAD) + slicing (PrusaSlicer) + STL inspection.

Headless: the OpenSCAD CLI exports STL without a display. PNG preview needs
xvfb-run (optional, only if installed).
"""

import json
import os
import shutil
import struct
import subprocess

from mcp.server.fastmcp import FastMCP

WORKDIR = os.path.expanduser(
    os.environ.get("MCP_CAD_WORKDIR", "~/cad-work")
)
os.makedirs(WORKDIR, exist_ok=True)

mcp = FastMCP("cad")


def _run(cmd: list, timeout: int = 120) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)[:4000]


def _read_stl_info(path: str) -> dict:
    """Parse a binary or ASCII STL: triangle count, file coherence."""
    with open(path, "rb") as f:
        head = f.read(5)
        if head == b"solid" and os.path.getsize(path) > 84:
            content = f.read().decode(errors="replace")
            n = content.count("facet normal")
            return {"format": "ascii", "triangles": n}
        # Binary: 80-byte header + uint32 count + 50 bytes/triangle
        f.seek(80)
        (n,) = struct.unpack("<I", f.read(4))
        size = os.path.getsize(path)
        expected = 84 + 50 * n
        return {
            "format": "binary",
            "triangles": n,
            "file_bytes": size,
            "expected_bytes": expected,
            "coherent": size == expected,
        }


@mcp.tool()
def cad_check() -> str:
    """Check that OpenSCAD and PrusaSlicer are installed, with versions."""
    oc = shutil.which("openscad")
    ps = shutil.which("prusa-slicer")
    out = {}
    if oc:
        r = subprocess.run([oc, "--version"], capture_output=True, text=True)
        out["openscad"] = r.stdout.strip() or r.stderr.strip()
    if ps:
        r = subprocess.run([ps, "--version"], capture_output=True, text=True)
        out["prusaslicer"] = (r.stdout.strip() or r.stderr.strip())[:80]
    out["workdir"] = WORKDIR
    return json.dumps(out)


@mcp.tool()
def cad_scad_to_stl(
    scad_code: str, name: str = "model", variables: str | None = None
) -> str:
    """Compile OpenSCAD source to STL (headless).
    variables: JSON object {"VAR": "value"} passed via -D (parametric overrides).
    Returns the STL path plus mesh info."""
    scad_file = os.path.join(WORKDIR, f"{name}.scad")
    stl_file = os.path.join(WORKDIR, f"{name}.stl")
    with open(scad_file, "w") as f:
        f.write(scad_code)
    cmd = ["openscad", "-o", stl_file]
    if variables:
        for k, v in json.loads(variables).items():
            cmd += ["-D", f"{k}={v}"]
    cmd.append(scad_file)
    rc, out = _run(cmd, timeout=300)
    if not os.path.exists(stl_file):
        return json.dumps({"error": "no output", "returncode": rc, "output": out})
    return json.dumps(
        {"stl": stl_file, "openscad_output": out, "mesh": _read_stl_info(stl_file)}
    )


@mcp.tool()
def cad_stl_info(stl_path: str) -> str:
    """Inspect an STL: format, triangle count, file coherence."""
    if not os.path.exists(stl_path):
        return json.dumps({"error": "not found", "path": stl_path})
    return json.dumps(_read_stl_info(stl_path))


@mcp.tool()
def cad_slice(
    stl_path: str, output_bgcode: str | None = None, profiles: str | None = None
) -> str:
    """Slice an STL to .bgcode via the PrusaSlicer CLI.
    profiles: semicolon-separated PrusaSlicer preset names, e.g.
    'Prusa XL 5T 0.4 nozzle;PLA;0.25mm SPEED'. If omitted, defaults apply."""
    if not os.path.exists(stl_path):
        return json.dumps({"error": "stl not found"})
    out = output_bgcode or os.path.join(
        WORKDIR, os.path.basename(stl_path).replace(".stl", ".bgcode")
    )
    cmd = ["prusa-slicer", "--export-gcode", "--output", out, stl_path]
    if profiles:
        cmd += ["--load", profiles]
    rc, outp = _run(cmd, timeout=600)
    result = {"returncode": rc, "output": outp, "target": out}
    if os.path.exists(out):
        result["bgcode_size"] = os.path.getsize(out)
    return json.dumps(result)


@mcp.tool()
def cad_stl_transform(
    stl_path: str,
    out_stl: str,
    scale: float | None = None,
    rotate_z: float | None = None,
    duplicate: int | None = None,
) -> str:
    """Transform an STL via the PrusaSlicer CLI (scale / rotate / duplicate)."""
    if not os.path.exists(stl_path):
        return json.dumps({"error": "stl not found"})
    cmd = ["prusa-slicer", "--export-stl", "--output", out_stl, stl_path]
    if scale is not None:
        cmd += ["--scale", str(scale)]
    if rotate_z is not None:
        cmd += ["--rotate", str(rotate_z)]
    if duplicate is not None:
        cmd += ["--duplicate", str(duplicate)]
    rc, out = _run(cmd, timeout=180)
    return json.dumps(
        {
            "returncode": rc,
            "output": out,
            "exists": os.path.exists(out_stl),
            "path": out_stl,
        }
    )


@mcp.tool()
def cad_preview_png(scad_code: str, name: str = "preview") -> str:
    """Render a PNG preview (requires xvfb-run). Returns the PNG path."""
    if not shutil.which("xvfb-run"):
        return json.dumps(
            {"error": "xvfb-run missing", "hint": "use cad_scad_to_stl instead"}
        )
    scad_file = os.path.join(WORKDIR, f"{name}.scad")
    png_file = os.path.join(WORKDIR, f"{name}.png")
    with open(scad_file, "w") as f:
        f.write(scad_code)
    rc, out = _run(
        [
            "xvfb-run", "-a", "openscad", "-o", png_file,
            "--imgsize", "800,600", "--colorscheme", "Tomorrow",
            scad_file,
        ],
        timeout=180,
    )
    return json.dumps(
        {
            "returncode": rc,
            "png": png_file,
            "exists": os.path.exists(png_file),
            "output": out,
        }
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
