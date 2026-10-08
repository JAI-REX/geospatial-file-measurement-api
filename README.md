# Geospatial File Measurement API

A FastAPI service that accepts KML files or ZIP archives containing ESRI Shapefiles, extracts geospatial features, handles CRS safely, and calculates measurements for supported geometries.

## Assignment coverage

| Requirement | Implementation |
|---|---|
| FastAPI | FastAPI application with OpenAPI/Swagger |
| KML upload | `POST /api/files/` |
| ZIP Shapefile upload | `POST /api/files/` |
| Feature ID/index | Returned per feature |
| Geometry type | Returned per feature |
| Geometry | GeoJSON geometry returned per feature |
| CRS | Source CRS returned per feature and file |
| Properties | Source attributes returned per feature |
| Polygon measurement | Area in m² |
| LineString measurement | Length in m |
| Point | No measurement |
| Geographic CRS | Transformed to projected CRS before measurement |
| File information | `GET /api/files/{id}/` |
| Measurements | `GET /api/files/{id}/measurements/` |
| Documentation | This README |
| Testing | Pytest suite |
| Health check | `GET /health` |
| Frontend | FastAPI-served HTML/CSS/JS dashboard |
| Docker | Dockerfile + health check |

## Tech stack

- Python 3.12
- FastAPI
- Uvicorn
- GeoPandas
- Shapely
- PyProj
- Fiona/GDAL
- Jinja2
- Pytest

## Project structure

```text
geospatial-api/
├── app/
│   ├── api/
│   │   └── files.py
│   ├── services/
│   │   └── geospatial.py
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/app.js
│   ├── templates/index.html
│   ├── main.py
│   └── store.py
├── sample_data/sample_test.kml
├── tests/
│   ├── test_health.py
│   └── test_geospatial.py
├── uploads/.gitkeep
├── Dockerfile
├── .dockerignore
├── .gitignore
├── pytest.ini
├── requirements.txt
└── README.md
```

## Local setup

### Windows CMD

```cmd
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

### Windows PowerShell

If PowerShell execution policy prevents activation, you do not need to activate the environment. Use the `.venv\Scripts\python.exe` commands above.

Alternatively, after Python 3.12 is installed:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Linux/macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open the web dashboard at `http://127.0.0.1:8000` and Swagger at `http://127.0.0.1:8000/docs`.

## Input requirements

Supported uploads:

1. `.kml`
2. `.zip` containing an ESRI Shapefile

A Shapefile ZIP should contain at least the matching `.shp`, `.shx`, and `.dbf` files. A `.prj` file is strongly recommended because it provides the source CRS.

The API enforces a 50 MB upload limit.

## API

### Health

```http
GET /health
```

Response:

```json
{"status":"ok"}
```

### Upload and process

```http
POST /api/files/
Content-Type: multipart/form-data
```

Form field: `file`

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/files/ \
  -F "file=@sample_data/sample_test.kml"
```

Example response:

```json
{
  "id": "abc123",
  "filename": "sample_test.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "measurement_crs": "EPSG:32643",
  "status": "COMPLETED"
}
```

### File information

```http
GET /api/files/{id}/
```

Returns file name, feature count, source CRS, measurement CRS and processing status.

### Measurements and feature details

```http
GET /api/files/{id}/measurements/
```

The response includes both feature details and measurements:

```json
{
  "file_id": "abc123",
  "source_crs": "EPSG:4326",
  "measurement_crs": "EPSG:32643",
  "features": [
    {
      "feature_id": "0",
      "geometry_type": "Polygon",
      "geometry": {
        "type": "Polygon",
        "coordinates": []
      },
      "crs": "EPSG:4326",
      "properties": {
        "name": "Test Polygon"
      }
    }
  ],
  "measurements": [
    {
      "feature_id": "0",
      "geometry_type": "Polygon",
      "measurement": 48765.21,
      "measurement_type": "Area",
      "unit": "m²"
    }
  ]
}
```

For LineString, `measurement_type` is `Length` and the unit is `m`. Point features return `measurement: null`, `measurement_type: null`, and `unit: null`.

## Architecture

```text
Client / Frontend / Swagger
          |
          v
     FastAPI Router
          |
          v
     Upload validation
          |
          v
   Geospatial processor
      /           \
     KML          ZIP
      |             |
      |        safe extraction
      |             |
      |        Shapefile reader
      \             /
       \           /
        GeoPandas
            |
            v
        CRS inspection
            |
            v
    Projected CRS selection
            |
            v
     Shapely measurements
            |
            v
      API response/store
```

### File-processing flow

1. FastAPI receives a multipart upload.
2. The extension is validated against `.kml` and `.zip`.
3. The upload is limited to 50 MB.
4. KML is read through GeoPandas/GDAL.
5. ZIP archives are checked for path traversal and symbolic links before extraction.
6. The archive must contain a complete Shapefile with `.shp`, `.shx`, and `.dbf`.
7. GeoPandas extracts features, attributes and source CRS.

### Measurement flow

- Polygon/MultiPolygon → projected geometry `.area` → m².
- LineString/MultiLineString → projected geometry `.length` → m.
- Point/MultiPoint → no measurement required.
- Unsupported geometry types are retained in the feature response and receive no measurement instead of crashing the request.

### CRS handling

Measurements must not be calculated directly from longitude/latitude degrees. If the source CRS is already projected, it is used directly. If the source CRS is geographic, GeoPandas estimates a local UTM CRS from the dataset and transforms the geometries before measuring them. The API reports both the source CRS and measurement CRS so the calculation is transparent.

If the input has no CRS and a measurement is required, the API rejects the file rather than silently assuming a CRS.

## Design decisions

### Why FastAPI?

FastAPI provides lightweight routing, multipart upload support, automatic OpenAPI documentation and a clean structure for a focused backend assessment.

### Why GeoPandas/Shapely/PyProj?

GeoPandas provides geospatial file reading and CRS-aware GeoDataFrames. Shapely provides geometry operations. PyProj supplies CRS definitions and transformations.

### Why local UTM for geographic coordinates?

A local UTM CRS gives measurements in metres and is generally more appropriate for local area and distance calculations than using raw geographic degrees. The selected CRS is exposed in the API response.

### Why in-memory storage?

The assessment implementation keeps metadata in memory and uploaded working files on local disk to avoid introducing a database that is not required by the specification. A process restart clears the in-memory records. For production, PostgreSQL/PostGIS plus object storage would be preferred.

### Why return GeoJSON geometry?

The assignment asks the API to identify the geometry for every feature. GeoJSON is a standard, frontend-friendly representation that can be consumed without exposing GeoPandas-specific Python objects.

## Error handling

Examples:

- Unsupported extension → HTTP 400
- File larger than 50 MB → HTTP 413
- Invalid/unsafe ZIP → HTTP 422
- ZIP without a complete Shapefile → HTTP 422
- Empty dataset → HTTP 422
- Missing CRS when measurements are required → HTTP 422
- Unknown file ID → HTTP 404
- Failed processing record → HTTP 409 for measurement retrieval

## Testing

Run:

```bash
pytest -q
```

The suite covers:

- Health endpoint
- Frontend route
- Unsupported file validation
- Missing file IDs
- KML upload
- Feature geometry/CRS/properties
- Polygon area
- LineString length
- Point no-measurement behavior
- Geographic-to-projected CRS handling
- ZIP Shapefile upload
- Unsafe ZIP rejection

## Docker

Build:

```bash
docker build -t geospatial-api .
```

Run:

```bash
docker run --rm -p 8000:8000 geospatial-api
```

Open `http://localhost:8000` or `http://localhost:8000/docs`.

The Docker image installs the GDAL/GEOS/PROJ system libraries required by common geospatial Python dependencies.

## Learning

This project demonstrates practical backend development with FastAPI, multipart file handling, geospatial file formats, GeoPandas, Shapely geometry operations, CRS transformations, API design, validation, automated testing, Docker, and a small browser frontend.

## Future scope

- PostgreSQL/PostGIS persistence
- Object storage such as S3-compatible storage
- Background jobs for large files
- Authentication and authorization
- Configurable upload limits
- Pagination for very large feature collections
- Streaming/async processing
- More geometry measurements and units
- Map visualization with Leaflet or MapLibre
- Observability, structured logging and metrics
- CI/CD and automated deployment

