# cad-mcp

MCP server for a **headless CAD → print** pipeline: model with OpenSCAD, export an STL, slice it to
G-code with PrusaSlicer, inspect the resulting mesh. Everything runs without a display.

## Why

Turning a language model into a usable CAD assistant means giving it a *chain* of tools, not one:
generate geometry → verify the mesh is coherent → slice with the right profiles → hand off to the
printer. Each step here is headless so it works over SSH and inside a container.

## Tools

| Tool | Purpose |
|---|---|
| `cad_check` | report OpenSCAD / PrusaSlicer presence and versions |
| `cad_scad_to_stl` | compile OpenSCAD source to STL (optional `-D` parameter overrides) |
| `cad_stl_info` | parse an STL: format, triangle count, file coherence |
| `cad_slice` | slice an STL to `.bgcode` with named PrusaSlicer profiles |
| `cad_stl_transform` | scale / rotate / duplicate an STL |
| `cad_preview_png` | render a PNG preview (needs `xvfb-run`) |

## Requirements

- `openscad` and `prusa-slicer` on `PATH`
- `python` + `mcp` (FastMCP v1)
- `xvfb-run` only for `cad_preview_png`

## Run

```bash
pip install "mcp<2"
python cad_mcp.py
```

## Notes

- `cad_scad_to_stl` passes parameters as `-D VAR=value`, so a single `.scad` file can be reused
  parametrically — useful when an agent iterates on dimensions.
- `cad_slice` takes a semicolon-separated list of profile names (PrusaSlicer preset syntax), which
  keeps printer/printer-material settings out of the code.

MIT.
