from __future__ import annotations

import math

import numpy as np
from build123d import (
    Align,
    Axis,
    BuildLine,
    BuildPart,
    BuildSketch,
    Cylinder,
    Line,
    Mode,
    Part,
    Plane,
    Spline,
    add,
    extrude,
    fillet,
    make_face,
)
from build123d import Polygon as BPolygon
from scipy.spatial import Voronoi
from shapely.geometry import LineString, Point
from shapely.geometry import Polygon as ShapelyPolygon

# ── Shapely ↔ build123d bridge ──────────────────────────────────────────────

def to_point2_tuple(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in coords]

def shape_to_polygons(geometry) -> list[ShapelyPolygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, ShapelyPolygon):
        return [geometry] if geometry.area > 1e-6 else []
    if hasattr(geometry, "geoms"):
        polys = []
        for g in geometry.geoms:
            polys.extend(shape_to_polygons(g))
        return polys
    return []

def add_shapely_polygon_to_sketch(polygon: ShapelyPolygon) -> None:
    if polygon.is_empty:
        return
    cleaned = polygon.buffer(0)
    if cleaned.is_empty:
        return
    if not isinstance(cleaned, ShapelyPolygon):
        polys = shape_to_polygons(cleaned)
        if not polys:
            return
        cleaned = max(polys, key=lambda p: p.area)
    exterior = to_point2_tuple(list(cleaned.exterior.coords)[:-1])
    if len(exterior) < 3:
        return
    BPolygon(*exterior)
    for interior in cleaned.interiors:
        hole = to_point2_tuple(list(interior.coords)[:-1])
        if len(hole) >= 3:
            BPolygon(*hole, mode=Mode.SUBTRACT)

def extrude_polygon(polygon: ShapelyPolygon, height: float) -> Part:
    with BuildPart() as p:
        with BuildSketch() as sk:
            add_shapely_polygon_to_sketch(polygon)
        extrude(sk.sketch, amount=height)
    return p.part


# ── Voronoi Generation ──────────────────────────────────────────────────────

def sunflower_points(count: int, radius: float) -> np.ndarray:
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    points: list[tuple[float, float]] = []
    for idx in range(count):
        r = radius * math.sqrt((idx + 0.5) / count)
        theta = idx * golden_angle
        points.append((r * math.cos(theta), r * math.sin(theta)))
    return np.array(points, dtype=float)

def voronoi_finite_polygons_2d(
    voronoi: Voronoi, radius: float
) -> tuple[list[list[int]], np.ndarray]:
    if voronoi.points.shape[1] != 2:
        raise ValueError("Voronoi input must be 2D")
    new_regions: list[list[int]] = []
    new_vertices = voronoi.vertices.tolist()
    center = voronoi.points.mean(axis=0)

    all_ridges: dict[int, list[tuple[int, int, int]]] = {}
    for (point_a, point_b), (vertex_a, vertex_b) in zip(
        voronoi.ridge_points, voronoi.ridge_vertices, strict=True
    ):
        all_ridges.setdefault(point_a, []).append((point_b, vertex_a, vertex_b))
        all_ridges.setdefault(point_b, []).append((point_a, vertex_a, vertex_b))

    for point_index, region_index in enumerate(voronoi.point_region):
        region = voronoi.regions[region_index]
        if all(vertex >= 0 for vertex in region):
            new_regions.append(region)
            continue
        ridges = all_ridges[point_index]
        new_region = [vertex for vertex in region if vertex >= 0]
        for neighbor_index, vertex_a, vertex_b in ridges:
            if vertex_b < 0:
                vertex_a, vertex_b = vertex_b, vertex_a
            if vertex_a >= 0:
                continue
            tangent = voronoi.points[neighbor_index] - voronoi.points[point_index]
            tangent_norm = np.linalg.norm(tangent)
            if tangent_norm <= 1e-9:
                continue
            tangent /= tangent_norm

            normal = np.array([-tangent[1], tangent[0]])
            midpoint = voronoi.points[[point_index, neighbor_index]].mean(axis=0)
            direction = np.sign(np.dot(midpoint - center, normal)) * normal

            far_point = voronoi.vertices[vertex_b] + direction * radius
            new_vertices.append(far_point.tolist())
            new_region.append(len(new_vertices) - 1)

        region_vertices = np.asarray([new_vertices[idx] for idx in new_region])
        region_center = region_vertices.mean(axis=0)
        angles = np.arctan2(
            region_vertices[:, 1] - region_center[1],
            region_vertices[:, 0] - region_center[0],
        )
        ordered = np.asarray(new_region)[np.argsort(angles)]
        new_regions.append(ordered.tolist())
    return new_regions, np.asarray(new_vertices)

def clip_to_seed_polygon(geometry, seed: np.ndarray) -> ShapelyPolygon | None:
    polygons = shape_to_polygons(geometry)
    if not polygons:
        return None
    seed_point = Point(float(seed[0]), float(seed[1]))
    containing = [
        poly for poly in polygons 
        if poly.contains(seed_point) or poly.touches(seed_point)
    ]
    if containing:
        return max(containing, key=lambda poly: poly.area)
    return min(polygons, key=lambda poly: poly.distance(seed_point))

def clipped_voronoi_cells(
    seeds: np.ndarray, clip_circle: ShapelyPolygon, far_radius: float
) -> list[ShapelyPolygon]:
    guard = np.array([
        [0.0, 0.0], [far_radius, 0.0], [-far_radius, 0.0], [0.0, far_radius],
        [0.0, -far_radius], [far_radius, far_radius], [far_radius, -far_radius],
        [-far_radius, far_radius], [-far_radius, -far_radius]
    ], dtype=float)
    all_points = np.vstack([seeds, guard])
    voronoi = Voronoi(all_points)
    regions, vertices = voronoi_finite_polygons_2d(voronoi, radius=far_radius * 2.0)

    cells: list[ShapelyPolygon] = []
    for index in range(len(seeds)):
        region_indices = regions[index]
        polygon_coords = vertices[region_indices]
        raw_polygon = ShapelyPolygon(polygon_coords)
        if raw_polygon.is_empty:
            continue
        clipped = raw_polygon.intersection(clip_circle)
        selected = clip_to_seed_polygon(clipped, seeds[index])
        if selected is None:
            continue
        cleaned = selected.buffer(0)
        if cleaned.is_empty:
            continue
        if isinstance(cleaned, ShapelyPolygon) and cleaned.area > 1.0:
            cells.append(cleaned)
    return cells

def centroidal_voronoi_cells(
    radius: float, seed_count: int = 42, relax_iterations: int = 3
) -> list[ShapelyPolygon]:
    clip_circle = Point(0.0, 0.0).buffer(radius, resolution=128)
    seeds = sunflower_points(seed_count, radius * 0.96)
    rng = np.random.default_rng(42)

    for _ in range(relax_iterations):
        cells = clipped_voronoi_cells(seeds, clip_circle, far_radius=radius * 8.0)
        if not cells:
            break
        centroids: list[tuple[float, float]] = []
        for cell in cells:
            centroid = cell.centroid
            centroids.append((float(centroid.x), float(centroid.y)))
        while len(centroids) < seed_count:
            jitter = rng.normal(0.0, 0.6, size=(2,))
            fill = sunflower_points(1, radius * 0.9)[0] + jitter
            centroids.append((float(fill[0]), float(fill[1])))
        seeds = np.array(centroids[:seed_count], dtype=float)

    return clipped_voronoi_cells(seeds, clip_circle, far_radius=radius * 8.0)

def louver_wall_thickness(radius: float, max_radius: float) -> float:
    # PA-CF: keep minimum at 1.6mm so slicers never skip a perimeter
    t = min(max(radius / max_radius, 0.0), 1.0)
    return 2.4 + (1.6 - 2.4) * t

def gaussian_displacement(radius: float, peak: float = 12.0, sigma: float = 26.0) -> float:
    return peak * math.exp(-(radius * radius) / (2.0 * sigma * sigma))


# ── Nautilus fin cross-section profile ──────────────────────────────────────

def nautilus_fin_edges(
    max_x: float,
    z_bottom: float,
    z_top: float,
    phase: float = 0.0,
    turns: float = 0.7,
    steps: int = 30,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Return (right_pts, left_pts) control points for B-spline fin edges.

    Designed for build123d Spline() which interpolates a smooth B-spline
    through the control points — zero faceting regardless of layer height.
    """
    height = z_top - z_bottom
    k = turns

    right_pts: list[tuple[float, float]] = []
    left_pts: list[tuple[float, float]] = []

    for i in range(steps + 1):
        t = i / steps
        z = z_bottom + t * height
        r = max_x * math.exp(-k * t)

        wave_r = math.sin(t * math.pi * 2.5 + phase) * max_x * 0.18 * math.sin(t * math.pi)
        right_pts.append((float(max(r + wave_r, 1.5)), float(z)))

        wave_l = math.sin(t * math.pi * 2.5 + phase - 0.3) * max_x * 0.18 * math.sin(t * math.pi)
        left_pts.append((float(min(-(r + wave_l), -1.5)), float(z)))

    return right_pts, left_pts


# ── The Main Louver Builder ─────────────────────────────────────────────────

def build_component_d_parametric_louver(*, fillets: bool = True) -> Part:
    """Component D: Horizontal Nautilus Fins + Voronoi Base.

    Parallel horizontal fins (like a wood-slice facade) whose XZ cross-section
    follows a logarithmic nautilus curve, flowing with height. The base is a
    Gaussian-displaced Voronoi lattice.
    """
    disc_diameter = 180.0
    disc_thickness = 5.0

    airflow_clip_diameter = 150.0
    airflow_radius = airflow_clip_diameter / 2.0

    # 150mm pipe socket (slips OVER the pipe, below the flange)
    # PA-CF: ~0.3–0.5% shrinkage; use +1.0mm radial clearance (≈ 2× PETG)
    pipe_od = 150.0
    socket_id = pipe_od + 1.0        # 151.0mm — PA-CF slip-over fit
    socket_wall = 2.5                # ring wall thickness
    socket_od = socket_id + 2.0 * socket_wall  # 155.6mm
    socket_length = 22.0             # depth of engagement over the pipe

    spire_height = 200.0
    fin_thickness = 1.6  # 0.4mm nozzle × 4 perimeters → solid, rigid fin
    fin_gap = 4.5
    pitch = fin_thickness + fin_gap

    num_fins = int(airflow_clip_diameter / pitch)
    start_y = -(num_fins - 1) * pitch / 2.0

    with BuildPart() as louver:
        # Outer flange (lip that rests on top of the pipe)
        Cylinder(
            disc_diameter / 2.0,
            disc_thickness,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        # Hollow out the airflow aperture through the flange
        Cylinder(
            airflow_radius,
            disc_thickness + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        )

        # Pipe socket ring (sits AROUND the pipe, extends downward)
        Cylinder(
            socket_od / 2.0,
            socket_length,
            align=(Align.CENTER, Align.CENTER, Align.MAX),  # MAX → grows down (-Z)
        )
        Cylinder(
            socket_id / 2.0,
            socket_length + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MAX),
            mode=Mode.SUBTRACT,
        )

        # Retention ring (thin inner shelf to support the Voronoi grille)
        Cylinder(
            airflow_radius,
            disc_thickness * 0.75,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        Cylinder(
            airflow_radius - 1.2,
            disc_thickness * 0.75 + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        )

        # 2. Gaussian Voronoi Base Grille
        clip_circle = Point(0.0, 0.0).buffer(airflow_radius, resolution=128)
        voronoi_cells = centroidal_voronoi_cells(airflow_radius, seed_count=36)

        for cell in voronoi_cells:
            centroid = cell.centroid
            radius = math.hypot(float(centroid.x), float(centroid.y))
            wall_thickness = louver_wall_thickness(radius, airflow_radius)

            boundary = LineString(cell.exterior.coords)
            wall_2d = boundary.buffer(
                wall_thickness / 2.0,
                cap_style=2,
                join_style=2,
            ).intersection(clip_circle)

            wall_polygons = shape_to_polygons(wall_2d)
            if not wall_polygons:
                continue

            wall_height = disc_thickness + gaussian_displacement(radius)
            for wall_polygon in wall_polygons:
                if wall_polygon.area < 0.4:
                    continue
                add(extrude_polygon(wall_polygon, wall_height))

        # 3. Horizontal Nautilus Fins
        for index in range(num_fins):
            y_pos = start_y + index * pitch

            if abs(y_pos) >= airflow_radius - 1.0:
                continue

            # Chord width at this Y within the circular boundary
            max_x = math.sqrt(airflow_radius**2 - y_pos**2)

            # Unique phase per fin → collective wave illusion across the array
            phase = y_pos * 0.09

            right_pts, left_pts = nautilus_fin_edges(
                max_x=max_x,
                z_bottom=disc_thickness,
                z_top=disc_thickness + spire_height,
                phase=phase,
                turns=0.7,
            )

            plane = Plane.XZ.offset(y_pos)

            with BuildPart() as fin_part:
                with BuildSketch(plane):
                    # BuildLine inside BuildSketch → Spline edges → make_face fills the region
                    with BuildLine():
                        Spline(right_pts)                      # right edge (bottom → top)
                        Line([right_pts[-1], left_pts[-1]])    # top cap
                        Spline(list(reversed(left_pts)))       # left edge (top → bottom)
                        Line([left_pts[0], right_pts[0]])      # bottom cap
                    make_face()
                extrude(amount=fin_thickness, both=True)

            add(fin_part.part)

        if fillets:
            target_edges = [
                edge for edge in louver.edges().filter_by(Axis.Z)
                if edge.length > 2.0
                and math.hypot(edge.center().X, edge.center().Y) < airflow_radius
            ]
            target_edges = sorted(
                target_edges, key=lambda e: e.length, reverse=True
            )[:50]
            try:
                fillet(target_edges, radius=0.5)
            except Exception:
                pass

    return louver.part.clean()
