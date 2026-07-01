# Rising Main Strip Builder - Function Reference

Notes on what each function in `Rising_Main_Strip_Builder_with_valves.ipynb` does, grouped by
pipeline stage rather than cell order.

## Pipeline overview

The notebook turns individual rising main segments into logical strips: runs of pipe that
trace continuously from a pump station or STP through to a manhole, without being split apart
or merged with unrelated parallel mains.

Three stages:

1. Geometry prep - split the mains at every true junction and at every site polygon boundary,
   so each segment has clean endpoints (`prepare_working_copy`).
2. Topology build - turn segment endpoints into a node graph using distance-based clustering,
   without moving any geometry (`build_topology`, `UnionFind`).
3. Tracing and attribution - walk the node graph to group segments into strips, then work out
   catchment, length, volume, and which pump station(s) belong to each strip (`trace_strips`,
   `assign_catchment`, `summarise_groups`, `write_attributes`).

## Generic / helper functions

### `log(msg)`
Writes to both the ArcGIS geoprocessing message pane (`arcpy.AddMessage`) and stdout, so
progress shows whether you're running inside Pro or from a plain Python console.

### `class UnionFind`
Disjoint-set with path compression. Backs both `build_topology` (clustering nearby endpoints
into one node) and `trace_strips` (grouping segments that share a node into one strip).

- `find(x)` - the root of whichever group `x` belongs to.
- `union(a, b)` - merges the groups containing `a` and `b`.

If two things get merged that shouldn't be, or fail to merge when they should, the bug is
almost always in what gets passed into `union()` (the distance/tolerance test upstream), not
in `UnionFind` itself.

### `keep_fields_mapping(in_fc, keep)`
Builds an `arcpy.FieldMappings` object keeping only the fields listed in `keep`, warning on any
that don't exist on the source. Used once, in `prepare_working_copy`, so the working copy
doesn't carry every field across from the source feature class.

### `build_point_index(fc, cell, id_field=None, sr=None)`
Coarse spatial hash of point coordinates for fast nearest-neighbour lookups, keyed by
`(x // cell, y // cell)`. This is what makes `nearest_id` fast - it checks the surrounding 3x3
block of grid cells instead of every feature in `fc`.

Only works for point geometries. `SHAPE@XY` on a polygon returns its centroid, which is why
matching to site polygons uses `match_nodes_to_polygons` instead.

### `nearest_id(pt, idx, cell, tol)`
Given a point and a spatial hash from `build_point_index`, returns the id of the nearest
indexed point within `tol` metres, or `None`. Searches the 3x3 neighbourhood of grid cells
around the point.

### `match_nodes_to_points(node_xy, fc, id_field, tol, sr=None)`
Matches each topology node to the nearest point feature in `fc` within `tol`. Used for
manholes (`mh_map`), since manhole endpoints are genuinely points. Not used against
`start_nodes` now that it's polygon-based - see `match_nodes_to_polygons`.

### `match_nodes_to_polygons(node_xy, fc, id_field, eps, sr=None)`
Polygon-aware matching for pump station / STP sites. For each topology node, checks whether the
coordinate falls inside or on the boundary of a site polygon, within `eps` (a small
float-precision tolerance, not a search radius). Uses each polygon's extent as a bounding-box
pre-filter before the exact `contains()` / `distanceTo()` test. Returns `{node_id: site_id}`.

### `match_pumps_to_segments(cfg, dist)`
Different question to the two functions above - not "which node touches which site" but "which
line segment is each pump/site nearest to, and how far away". Uses `arcpy.analysis.Near`
(works natively on polygon inputs, measuring boundary-to-line distance) to build
`{pump_id: (segment_oid, distance)}`. Feeds `assign_catchment`, which needs a segment-level
anchor point to propagate catchment out from.

## Pipeline functions

### `prepare_working_copy(cfg)`
First real step. In order:

1. Creates the file geodatabase if it doesn't exist.
2. Exports a trimmed copy of the raw rising mains (`work_raw`), keeping only the fields in
   `cfg.keep_fields`, and repairs any null/invalid geometry.
3. Nodes true tees: generates points at every line endpoint (`FeatureVerticesToPoints`,
   `BOTH_ENDS`), then splits lines with `SplitLineAtPoint` using a small `node_tolerance` so
   only genuine end-to-end junctions get split, not crossings or overlaps.
4. Splits at site polygons: converts the pump station / STP polygons to boundary lines
   (`PolygonToLine`), intersects them with the mains to get exact touch/cross points, then
   splits the mains there. This turns a main passing through a pump station site into two
   segments meeting at a clean node.
5. Optionally repeats the split against manholes if `treat_manholes_as_barriers` is `True`.

Output: `cfg.working_fc`, the fully-split, original-geometry working copy everything else
operates on.

### `calculate_length(cfg)`
Adds `SEG_LEN_M`, populated via `CalculateGeometryAttributes` using the projected CRS
(`target_epsg`). This planar length is what every downstream length/volume figure is built
from - if strips look the wrong length, check this ran against a properly projected
coordinate system.

### `calculate_pipe_volumes(cfg)`
Per-segment diameter (mm to m), cross-sectional area, and volume:

```
AREA_M2 = pi * (DIAM_M / 2)^2
VOL_M3  = AREA_M2 * SEG_LEN_M
```

Reads diameter from `NominalDiameter` - change the `dn_field` variable inside the function if
your source field is named differently. Rows with a null diameter get null area/volume rather
than erroring or defaulting to zero.

### `read_segments(cfg)`
Reads every segment's first/last point and length into two plain dicts (`seg_geo`, `seg_len`),
keyed by OID. Everything from here through `trace_strips` works on these dicts, not on the
feature class directly.

### `build_topology(seg_geo, tol)`
Clusters segment endpoints within `tol` of each other into a shared node, using the same
grid-bucket plus `UnionFind` approach as the point-matching helpers, applied to all endpoints
against each other.

Returns:
- `node_xy` - `{node_id: (x, y)}`, the averaged coordinate of each cluster.
- `seg_node_ids` - `{segment_oid: (start_node_id, end_node_id)}`.

This is the function most likely to cause false merges. Clustering is pairwise - if A is
within `tol` of B, and B is within `tol` of C, A and C end up in the same node even if A and C
are up to `2 * tol` apart. On tightly-spaced parallel mains this can chain a whole run of
unrelated endpoints together, so keep `node_tolerance` as tight as the source data allows.

### `trace_strips(seg_node_ids, barrier_nodes)`
Unions segments that share a node, except where that node is a barrier (a pump station, or
optionally a manhole). This is what turns individual segments into strips - a strip is
everything reachable from everything else without crossing a barrier.

Returns: `{segment_oid: group_id}`.

### `assign_catchment(seg_node_ids, pump_seg, pump_catch)`
Deliberately ignores barriers. Unions everything that shares a node regardless of whether that
node is a pump station, to find the full physically connected component - trunk plus every
fork off it. Each component then inherits the catchment value of whichever matched pump is
nearest to any segment in that component. This means a fork that traces out as its own
separate strip still gets the correct catchment, because catchment follows physical
connectivity, not strip boundaries.

Returns: `{segment_oid: catchment_value}`.

### `summarise_groups(seg_node_ids, seg_len, seg_catchment, group_of_seg, start_map, mh_map)`
Rolls everything up to strip (group) level:

- `group_len` - total length per strip.
- `group_catch` - catchment per strip (all segments in a strip share one physical component, so
  they agree).
- `group_start_id` - the first matched pump/site id encountered per strip. Order depends on
  dict iteration order - treat this as "a" start id, not necessarily "the primary" one.
- `group_all_starts` - every matched pump/site id per strip, deduplicated, joined into one
  semicolon-separated string (`ALL_SPS`). This is what shows a strip has two pump stations on
  it, rather than silently dropping the second one.
- `group_starts_z` / `group_ends_mh` - 1/0 flags for whether the strip touches a start node or
  manhole at all, only populated if `cfg.validate_endpoints` is `True`.

### `write_attributes(cfg, ...)`
Adds the strip-level fields (`GROUP_ID`, `GRP_LEN_M`, `SRC_CATCH`, `START_ID`, `ALL_SPS`, and
optionally `STARTS_Z`/`ENDS_MH`) to `working_fc` and writes per-strip values onto every segment
row via an `UpdateCursor`.

If `summarise_groups` ever changes what it returns, this function's parameter list and the
`fields` list inside it both need updating together - a mismatch throws a `TypeError` about
positional arguments, not anything more descriptive.

### `export_outputs(cfg)`
Copies `working_fc` straight to `out_shp` (segment-level shapefile), and separately writes
`out_csv` with a wider field list (adds `DIAM_M`, `AREA_M2`, `VOL_M3` and the keep fields).
Both are still one row per segment, not per strip.

### `merge_strips(cfg)`
Dissolves `working_fc` by `GROUP_ID` into `out_merged`, one row per strip. Sums length and
volume, takes the first catchment/start-id/all-starts value (all segments in a group already
agree, so `FIRST` is safe), and counts plus concatenates the Maximo asset ids that make up the
strip (`N_SEG`, `MX_LIST`). Field renaming from ArcGIS's auto-generated `SUM_`/`FIRST_`/
`COUNT_`/`CONCATENATE_` prefixes happens right after the dissolve.

### `main(cfg=None)`
Runs the whole pipeline in order: `prepare_working_copy`, `calculate_length`,
`calculate_pipe_volumes`, `read_segments`, `build_topology`, `match_nodes_to_polygons` (pumps/
sites), `match_nodes_to_points` (manholes), `trace_strips`, `match_pumps_to_segments`,
`assign_catchment`, `summarise_groups`, `write_attributes`, `export_outputs`, `merge_strips`.

Also sets the environment (`overwriteOutput`, `addOutputsToMap = False` to avoid schema locks,
and forces `outputCoordinateSystem` to `target_epsg`, required for length calculations to be
correct). Logs a summary count of strips and any strips with no catchment at the end.

## Troubleshooting

| Symptom | Likely cause | Where to look |
|---|---|---|
| Two unrelated mains merged into one strip | Chained clustering in endpoint matching | `build_topology`, tighten `node_tolerance` |
| A strip has no catchment | No pump matched within `dist` in `match_pumps_to_segments`, or that pump has a blank catchment field | `assign_catchment`, `cfg.start_catch_field` |
| Pump station not recognised as a barrier | Node didn't fall inside/on the site polygon within `site_touch_eps` | `match_nodes_to_polygons` |
| Main not split where it clearly crosses a site | No true boundary-crossing point generated | `prepare_working_copy`, the `PolygonToLine`/`Intersect` step - check if the main's endpoint sits inside the polygon without crossing the boundary |
| `TypeError: takes N positional arguments but M were given` | A function definition cell is stale (call site was edited but the def cell wasn't re-run) | Re-run the def cell, then every cell that calls it, in order |
| Strip missing a second pump station in `START_ID` | Expected - `START_ID` only ever holds the first-encountered id | Check `ALL_SPS` instead |
