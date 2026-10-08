from __future__ import annotations

import json
import math
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import geopandas as gpd
from pyproj import CRS
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon, mapping


class GeospatialError(Exception):
    """Expected, user-facing geospatial processing error."""


def choose_projected_crs(gdf: gpd.GeoDataFrame) -> CRS:
    if gdf.crs is None:
        raise GeospatialError(
            "Input file has no CRS. A CRS is required for safe area/length calculations."
        )

    source = CRS.from_user_input(gdf.crs)
    if source.is_projected:
        return source

    estimated = gdf.estimate_utm_crs()
    if estimated is None:
        # Fallback for unusual/global data. UTM is preferred whenever possible.
        estimated = CRS.from_epsg(3395)
    return CRS.from_user_input(estimated)


def _safe_extract_zip(zip_path: Path, output_dir: Path) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = archive.infolist()
            if not members:
                raise GeospatialError("ZIP archive is empty.")

            root = output_dir.resolve()
            for member in members:
                # Reject absolute paths and path traversal.
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise GeospatialError("Unsafe ZIP archive: path traversal detected.")

                target = (output_dir / member.filename).resolve()
                if target != root and root not in target.parents:
                    raise GeospatialError("Unsafe ZIP archive.")

                # Reject symlink entries.
                mode = (member.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise GeospatialError("Unsafe ZIP archive: symbolic links are not allowed.")

            archive.extractall(output_dir)
            return [member.filename for member in members]
    except zipfile.BadZipFile as exc:
        raise GeospatialError("Uploaded file is not a valid ZIP archive.") from exc


def extract_zip(zip_path: Path, output_dir: Path) -> Path:
    _safe_extract_zip(zip_path, output_dir)

    shp_files = [
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".shp"
    ]
    if not shp_files:
        raise GeospatialError("ZIP archive does not contain a Shapefile (.shp).")

    # A usable Shapefile needs the core companion files beside the .shp.
    candidates: list[Path] = []
    for shp in shp_files:
        stem = shp.with_suffix("")
        has_shx = stem.with_suffix(".shx").exists() or stem.with_suffix(".SHX").exists()
        has_dbf = stem.with_suffix(".dbf").exists() or stem.with_suffix(".DBF").exists()
        if has_shx and has_dbf:
            candidates.append(shp)

    if not candidates:
        raise GeospatialError(
            "ZIP contains .shp files, but no complete Shapefile with required .shx and .dbf files."
        )

    return candidates[0]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element.iter() if _local_name(child.tag) == name]


def _coordinates(element: ET.Element) -> list[tuple[float, float]]:
    coordinate_nodes = _find_children(element, "coordinates")
    if not coordinate_nodes or not coordinate_nodes[0].text:
        raise GeospatialError("KML geometry is missing coordinates.")

    points: list[tuple[float, float]] = []
    for token in coordinate_nodes[0].text.replace("\n", " ").split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            points.append((float(parts[0]), float(parts[1])))
        except ValueError as exc:
            raise GeospatialError("KML contains invalid coordinates.") from exc
    if not points:
        raise GeospatialError("KML geometry contains no valid coordinates.")
    return points


def _parse_kml_geometry(element: ET.Element) -> Any:
    geometry_nodes = [child for child in element if _local_name(child.tag) in {
        "Point", "LineString", "Polygon", "MultiGeometry"
    }]
    if not geometry_nodes:
        # Placemark itself may contain geometry deeper in the tree.
        geometry_nodes = [child for child in element.iter() if child is not element and _local_name(child.tag) in {
            "Point", "LineString", "Polygon", "MultiGeometry"
        }]
    if not geometry_nodes:
        return None

    node = geometry_nodes[0]
    kind = _local_name(node.tag)

    if kind == "Point":
        return Point(_coordinates(node)[0])
    if kind == "LineString":
        coords = _coordinates(node)
        return LineString(coords)
    if kind == "Polygon":
        rings = [ring for ring in node.iter() if _local_name(ring.tag) == "LinearRing"]
        if not rings:
            raise GeospatialError("KML polygon has no LinearRing geometry.")
        shell = _coordinates(rings[0])
        holes = [_coordinates(ring) for ring in rings[1:]]
        return Polygon(shell, holes)
    if kind == "MultiGeometry":
        geometries = []
        for child in node:
            if _local_name(child.tag) in {"Point", "LineString", "Polygon", "MultiGeometry"}:
                geom = _parse_kml_geometry(child)
                if geom is not None:
                    geometries.append(geom)
        if not geometries:
            return None
        types = {geom.geom_type for geom in geometries}
        if types == {"Point"}:
            return MultiPoint(geometries)
        if types == {"LineString"}:
            return MultiLineString(geometries)
        if types == {"Polygon"}:
            return MultiPolygon(geometries)
        return GeometryCollection(geometries)

    return None


def _read_kml(file_path: Path) -> gpd.GeoDataFrame:
    try:
        root = ET.parse(file_path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise GeospatialError(f"Unable to parse KML file: {exc}") from exc

    placemarks = [element for element in root.iter() if _local_name(element.tag) == "Placemark"]
    rows: list[dict[str, Any]] = []

    for index, placemark in enumerate(placemarks):
        geometry = _parse_kml_geometry(placemark)
        if geometry is None:
            continue

        properties: dict[str, Any] = {}
        for child in placemark:
            name = _local_name(child.tag)
            if name == "name" and child.text:
                properties["name"] = child.text.strip()
            elif name == "description" and child.text:
                properties["description"] = child.text.strip()
            elif name == "ExtendedData":
                for data in child.iter():
                    if _local_name(data.tag) != "Data":
                        continue
                    key = data.attrib.get("name")
                    value_nodes = [v for v in data if _local_name(v.tag) == "value"]
                    if key and value_nodes and value_nodes[0].text is not None:
                        properties[key] = value_nodes[0].text.strip()

        rows.append({"feature_id": index, **properties, "geometry": geometry})

    if not rows:
        raise GeospatialError("The KML file contains no supported Placemark geometries.")

    # KML coordinates are longitude/latitude in WGS84.
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def load_geodata(file_path: Path, work_dir: Path) -> gpd.GeoDataFrame:
    suffix = file_path.suffix.lower()

    if suffix == ".kml":
        return _read_kml(file_path)
    if suffix == ".zip":
        shp = extract_zip(file_path, work_dir / "shapefile")
        try:
            gdf = gpd.read_file(shp)
        except Exception as exc:
            raise GeospatialError(f"Unable to read Shapefile: {exc}") from exc
    else:
        raise GeospatialError("Unsupported file type. Upload a .kml or .zip Shapefile archive.")

    if gdf.empty:
        raise GeospatialError("The uploaded geospatial file contains no features.")
    if "geometry" not in gdf.columns:
        raise GeospatialError("The uploaded dataset does not contain a geometry column.")

    return gdf

def clean_value(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def geometry_json(geometry: Any) -> dict | None:
    if geometry is None or geometry.is_empty:
        return None
    return mapping(geometry)


def process_file(file_path: Path, work_dir: Path) -> dict[str, Any]:
    gdf = load_geodata(file_path, work_dir)

    source_crs = gdf.crs.to_string() if gdf.crs else None
    measurement_crs = None
    projected = None

    measurement_needed = gdf.geometry.geom_type.isin(
        ["Polygon", "MultiPolygon", "LineString", "MultiLineString"]
    ).any()

    if measurement_needed:
        measurement_crs_obj = choose_projected_crs(gdf)
        measurement_crs = measurement_crs_obj.to_string()
        try:
            projected = gdf.to_crs(measurement_crs_obj)
        except Exception as exc:
            raise GeospatialError(f"Unable to transform geometry to measurement CRS: {exc}") from exc

    features: list[dict[str, Any]] = []
    measurements: list[dict[str, Any]] = []

    for position, (idx, row) in enumerate(gdf.iterrows()):
        geom = row.geometry
        geom_type = geom.geom_type if geom is not None else "Unknown"
        properties = {
            str(key): clean_value(value)
            for key, value in row.items()
            if key != "geometry"
        }

        features.append(
            {
                "feature_id": str(idx),
                "geometry_type": geom_type,
                "geometry": geometry_json(geom),
                "crs": source_crs,
                "properties": properties,
            }
        )

        measurement: dict[str, Any] = {
            "feature_id": str(idx),
            "geometry_type": geom_type,
            "measurement": None,
            "measurement_type": None,
            "unit": None,
        }

        if projected is not None:
            projected_geometry = projected.iloc[position].geometry
            if geom_type in ("Polygon", "MultiPolygon"):
                measurement.update(
                    measurement=round(float(projected_geometry.area), 6),
                    measurement_type="Area",
                    unit="m²",
                )
            elif geom_type in ("LineString", "MultiLineString"):
                measurement.update(
                    measurement=round(float(projected_geometry.length), 6),
                    measurement_type="Length",
                    unit="m",
                )

        measurements.append(measurement)

    return {
        "feature_count": len(features),
        "crs": source_crs,
        "measurement_crs": measurement_crs,
        "features": features,
        "measurements": measurements,
    }
