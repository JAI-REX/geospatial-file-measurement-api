from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

KML = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Polygon</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
77.5940,12.9710,0 77.5960,12.9710,0 77.5960,12.9730,0 77.5940,12.9730,0 77.5940,12.9710,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Line</name><LineString><coordinates>77.5940,12.9710,0 77.5960,12.9730,0</coordinates></LineString></Placemark>
<Placemark><name>Point</name><Point><coordinates>77.5950,12.9720,0</coordinates></Point></Placemark>
</Document></kml>'''


def test_kml_upload_and_measurements():
    response = client.post(
        "/api/files/",
        files={"file": ("sample.kml", KML.encode(), "application/vnd.google-earth.kml+xml")},
    )
    assert response.status_code == 201, response.text
    uploaded = response.json()
    assert uploaded["feature_count"] == 3
    assert uploaded["crs"]
    assert uploaded["measurement_crs"]

    info = client.get(f"/api/files/{uploaded['id']}/")
    assert info.status_code == 200

    result = client.get(f"/api/files/{uploaded['id']}/measurements/")
    assert result.status_code == 200
    payload = result.json()
    assert len(payload["features"]) == 3
    assert len(payload["measurements"]) == 3

    polygon = next(m for m in payload["measurements"] if m["geometry_type"] == "Polygon")
    line = next(m for m in payload["measurements"] if m["geometry_type"] == "LineString")
    point = next(m for m in payload["measurements"] if m["geometry_type"] == "Point")

    assert polygon["measurement_type"] == "Area"
    assert polygon["unit"] == "m²"
    assert polygon["measurement"] > 0
    assert line["measurement_type"] == "Length"
    assert line["unit"] == "m"
    assert line["measurement"] > 0
    assert point["measurement"] is None
    assert point["measurement_type"] is None

    feature = payload["features"][0]
    assert feature["geometry"] is not None
    assert feature["crs"]
    assert "properties" in feature


def test_zip_shapefile_upload(tmp_path: Path):
    layer_dir = tmp_path / "layer"
    layer_dir.mkdir()
    gdf = gpd.GeoDataFrame(
        {"name": ["parcel"]},
        geometry=[Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98), (77.59, 12.97)])],
        crs="EPSG:4326",
    )
    shp_path = layer_dir / "parcel.shp"
    gdf.to_file(shp_path, driver="ESRI Shapefile")

    archive = tmp_path / "parcel.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in layer_dir.iterdir():
            zf.write(path, arcname=path.name)

    response = client.post(
        "/api/files/",
        files={"file": ("parcel.zip", archive.read_bytes(), "application/zip")},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["feature_count"] == 1
    assert payload["crs"]


def test_unsafe_zip_rejected():
    import io
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as zf:
        zf.writestr("../../evil.shp", b"bad")
    response = client.post(
        "/api/files/",
        files={"file": ("unsafe.zip", data.getvalue(), "application/zip")},
    )
    assert response.status_code == 422
    assert "Unsafe ZIP" in response.json()["detail"]
