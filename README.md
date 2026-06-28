# Rising Main Strip Builder

- ArcGIS Version: ArcGIS Pro 3.2.0
- ArcPy Version:  3.2
- Python Version: Python 3.10.0
- Dependencies:   arcpy, os, pandas, collections, dataclasses, typing

An ArcGIS Pro / `arcpy` pipeline (Jupyter notebook) that groups sewer rising main pipe segments into connected "strips", meaning continuous runs from a pump station through to a discharge point. Each strip is given a shared group ID, a total length, the catchment of its start point, and endpoint validation flags. The segments are then dissolved into a single output layer. This is a live project that is still WIP.

## What it does

Given a rising mains line layer plus point layers for pump stations (start nodes) and manholes, the pipeline:

1. Stages the data. Exports the mains to a working copy, repairs geometry, and reprojects everything to a common projected CRS (GDA2020 MGA Zone 56, EPSG:7856). Inputs in other coordinate systems such as Web Mercator are reprojected on read, so all geometry is compared in metres.
2. Nodes the network. Splits the mains at pipe endpoints so a branch teeing into a trunk creates a shared node. Endpoint-only noding is used deliberately, because it avoids snapping mid-span crossings or colinear overlaps that aren't real connections.
3. Splits at structures. Splits the mains at pump stations and manholes so strips can start and terminate at the right assets.
4. Builds topology. Clusters segment endpoints within a small tolerance into shared nodes.
5. Traces strips. Uses a Union-Find (disjoint-set) structure to group all segments connected through shared nodes into one strip, while respecting network barriers.
6. Summarises each strip. Records total length, the catchment taken from the strip's start point, the retained start-point ID, and flags for whether the strip starts at a pump station and ends at a manhole.
7. Writes and dissolves. Writes per-segment attributes, then dissolves by group ID into a single merged strips layer.

## Requirements


- ArcGIS Pro with an active `arcpy` Python environment (the notebook runs inside ArcGIS Pro's Jupyter kernel)
- Input feature classes: rising mains (lines), pump stations / start nodes (points), manholes (points)

## Configuration

All settings live in the `Config` dataclass at the top of the notebook. The main fields are:

| Field | Purpose |
|---|---|
| `rising_mains`, `start_nodes`, `manholes` | Input feature class paths |
| `out_merged` | Output dissolved strips layer |
| `target_epsg` | Working CRS (projected, metres) |
| `catchment_field` | Catchment attribute on the pipe, used as a QA cross-check |
| `start_catch_field` | Catchment attribute read from the start node, which is the source of `SRC_CATCH` |
| `start_id_field` | ID field on the start node, retained at strip level |
| `connect_tolerance` | Search radius for splitting a main at a structure |
| `node_tolerance` | How close two pipe ends must be to count as connected (keep this small) |
| `endpoint_tolerance` | How close a node must sit to a pump station or manhole to match |
| `treat_manholes_as_barriers` | Whether manholes break a strip |

## Usage

1. Open the notebook in ArcGIS Pro.
2. Edit the `Config` paths and field names to match your data.
3. Use Kernel then Restart and Run All.
4. Check the log line `-> N strips from M matched pump stations`. The dissolved output is written to `out_merged`.

## Outputs

A dissolved line layer where each feature is one strip, with fields including:

- `GROUP_ID`, the strip identifier
- `GRP_LEN_M`, total strip length in metres
- `SRC_CATCH`, catchment from the strip's start point
- `START_ID`, retained start-point ID
- `STARTS_Z` and `ENDS_MH`, endpoint validation flags

## Notes and limitations

CRS is important for connectivity with nodes. General pipe connectivity isn't impacted, but search distance to the nearest SPS/STP/manhole will be. Raw `SearchCursor` uses the working CRS, so if a pump-station match returns zero, check that all inputs reproject to `target_epsg` correctly. This is printed in the notebook.

The tolerances are decoupled. `connect_tolerance` is the structure-split radius and `node_tolerance` is the connection threshold. Keep `node_tolerance` above any genuine drawn gap but well below the spacing of parallel mains. These tolerances were identified through trial and error, and is heavily driven by known geometry issues with the input data. These will be mostly resolved with utility network.

Endpoint-only noding groups true tees, where a pipe ends on another, but ignores crossings and overlaps where neither pipe terminates. A pipe tapped into the exact middle of another with no vertex there is a rare case that won't node. There are multiple parts of the network where two seperate rising mains overlap, and without endpoint-only noding, these became a large combined strip.
