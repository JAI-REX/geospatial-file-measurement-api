# Geospatial File Measurement API

## About the project

I built this project as a backend API for working with basic geospatial files. The main idea is to upload a KML file or a ZIP file containing an ESRI Shapefile, read the features from it, identify their geometry and CRS, and calculate measurements where possible.

I used FastAPI for the backend and GeoPandas/Shapely for the geospatial processing. I also added a small web interface so the API can be tested without using only Postman or Swagger.

The project follows the requirements given in the assignment and also includes validation, error handling, tests, and Docker support.

## What the project does

The API can:

- Accept `.kml` files.
- Accept `.zip` files containing an ESRI Shapefile.
- Extract the features from the uploaded file.
- Return a feature ID/index for every feature.
- Return the geometry type and GeoJSON geometry.
- Return the CRS used by the source file.
- Return the attributes/properties of each feature.
- Calculate area for Polygon and MultiPolygon features.
- Calculate length for LineString and MultiLineString features.
- Skip measurement for Point features.
- Avoid calculating measurements directly from latitude/longitude degrees.
- Transform geographic data to a suitable projected CRS before calculating area or length.
- Handle unsupported or invalid files with proper error messages.

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
- HTML, CSS and JavaScript
- Docker

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
├── sample_data/
│   ├── sample_test.kml
│   └── sample_shapefile.zip
├── tests/
│   ├── test_health.py
│   └── test_geospatial.py
├── uploads/
├── Dockerfile
├── .dockerignore
├── .gitignore
├── pytest.ini
├── requirements.txt
└── README.md
```

## How to run the project

I used Python 3.12 for this project because the geospatial Python packages are easier to install and use with this version.

### Windows

Create a virtual environment:

```cmd
py -3.12 -m venv .venv
```

Install the required packages:

```cmd
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the API:

```cmd
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

Swagger documentation is available at:

```text
http://127.0.0.1:8000/docs
```

If PowerShell does not allow virtual-environment activation, I can still run the project by using `.venv\Scripts\python.exe` directly as shown above.

### Linux/macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Input files

The API accepts two types of files:

1. `.kml`
2. `.zip` containing an ESRI Shapefile

For a Shapefile ZIP, the required `.shp`, `.shx`, and `.dbf` files should be present. A `.prj` file is recommended because it contains the CRS information.

The upload size is limited to 50 MB.

### KML processing

The KML reader is implemented directly in Python using XML parsing. I did this so that the project does not depend on whether the local GDAL installation has the KML driver enabled.

KML coordinates are treated as WGS84 (`EPSG:4326`), and measurements are calculated only after transforming the geometries to a suitable projected CRS.

## API endpoints

### 1. Health check

```http
GET /health
```

Example response:

```json
{
  "status": "ok"
}
```

### 2. Upload a file

```http
POST /api/files/
Content-Type: multipart/form-data
```

The form field is called `file`.

Example using curl:

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

The exact measurement CRS can be different depending on the location of the uploaded data.

### 3. Get file information

```http
GET /api/files/{id}/
```

This returns the uploaded file name, number of features, source CRS, measurement CRS and processing status.

### 4. Get measurements and feature details

```http
GET /api/files/{id}/measurements/
```

Example response:

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

For LineString and MultiLineString, the measurement type is `Length` and the unit is metres (`m`). Point features do not need a measurement, so their measurement fields are `null`.

## Architecture

The application is divided into a few simple parts:

```text
User / Web UI / Swagger
          |
          v
      FastAPI API
          |
          v
    Upload validation
          |
          v
  Geospatial processing
       /         \
     KML          ZIP
      |             |
   XML parser    Safe extraction
      |             |
      |          Shapefile
      |            reader
       \           /
        \         /
         GeoDataFrame
              |
              v
          CRS check
              |
              v
      Projected CRS selection
              |
              v
       Area / Length
          calculation
              |
              v
          API response
```

### File-processing flow

1. The client uploads a file using the API or the web interface.
2. The API checks the file extension.
3. The upload is limited to 50 MB.
4. KML files are parsed using the Python XML parser.
5. ZIP files are checked for unsafe paths and symbolic links before extraction.
6. The ZIP must contain a complete Shapefile with the required `.shp`, `.shx` and `.dbf` files.
7. The geospatial data is converted into a GeoDataFrame.
8. The feature geometry, attributes and CRS are collected.

### Measurement flow

For measurements, I use the geometry type to decide what calculation is needed:

- **Polygon / MultiPolygon:** calculate area in square metres (`m²`).
- **LineString / MultiLineString:** calculate length in metres (`m`).
- **Point:** no measurement is required.
- **Other/unsupported geometry:** keep the feature information but do not calculate a measurement.

## CRS handling

One important part of this project is handling CRS correctly.

Area and length should not be calculated directly from longitude and latitude because geographic coordinates are measured in degrees. Before calculating measurements, I check the source CRS.

- If the source CRS is already projected, I use that projected CRS.
- If the source CRS is geographic, I estimate a suitable local UTM CRS using GeoPandas.
- The geometries are transformed to that CRS before calculating area or length.
- The API returns both the original CRS and the measurement CRS so it is clear how the calculation was performed.

If a file needs a measurement but does not have a CRS, the API returns an error instead of assuming a CRS.

## Design decisions

### Why I used FastAPI

I chose FastAPI because it is simple to build APIs with, supports file uploads easily, provides automatic Swagger documentation, and was a good fit for this assignment.

### Why I used GeoPandas and Shapely

GeoPandas makes it easier to work with geospatial files and CRS information. Shapely provides the geometry objects and the area/length calculations. PyProj is used for CRS information and transformations.

### Why I used a projected CRS for measurements

Using longitude and latitude directly can give incorrect area and distance values because the coordinates are in degrees. A suitable projected CRS gives measurements in metres, which makes the results more useful.

### Why I used in-memory storage

For this assignment, I kept the processed file information in memory instead of adding a database. This keeps the project small and focused on the required functionality. The records are cleared if the application restarts.

For a production version, I would use PostgreSQL/PostGIS for storing geospatial information and object storage for uploaded files.

### Why I return GeoJSON geometry

I return the geometry in GeoJSON format because it is a standard format and can be easily used by frontend applications or mapping libraries.

## Error handling

The API handles common invalid cases instead of letting the application crash.

Examples include:

- Unsupported file extension → `400`
- File larger than 50 MB → `413`
- Invalid or unsafe ZIP → `422`
- ZIP without a complete Shapefile → `422`
- Empty dataset → `422`
- Missing CRS when a measurement is required → `422`
- Unknown file ID → `404`
- Trying to get measurements for a failed upload → `409`

## Testing

I added automated tests using Pytest.

Run them with:

```bash
pytest -q
```

The tests cover:

- Health endpoint
- Frontend route
- Unsupported file validation
- Unknown file ID
- KML upload
- Feature geometry, CRS and properties
- Polygon area calculation
- LineString length calculation
- Point no-measurement behavior
- CRS transformation for measurements
- ZIP Shapefile upload
- Unsafe ZIP rejection

## Docker

I also added Docker support so the application can be run in a consistent environment.

Build the image:

```bash
docker build -t geospatial-api .
```

Run it:

```bash
docker run --rm -p 8000:8000 geospatial-api
```

Then open:

```text
http://localhost:8000
```

or:

```text
http://localhost:8000/docs
```

The Docker image installs the required GDAL, GEOS and PROJ system libraries for the geospatial Python packages.

## What I learned

While making this project, I got practical experience with FastAPI file uploads, API endpoint design, geospatial file formats, GeoPandas, Shapely, CRS transformations, validation and error handling. I also learned why CRS matters when calculating area and distance and why geographic coordinates should not be used directly for those calculations.

I also worked with automated testing and Docker so the application can be tested and run in a more consistent environment.

## Future improvements

If I continue this project, I would like to add:

- PostgreSQL/PostGIS database support.
- Cloud/object storage for uploaded files.
- Background processing for large files.
- Authentication and authorization.
- Pagination for large numbers of features.
- More measurement types and units.
- A proper interactive map using Leaflet or MapLibre.
- Better logging and monitoring.
- CI/CD for automated testing and deployment.

## Assignment requirement checklist

Before submission, I checked the main requirements of the assignment:

- [x] FastAPI backend
- [x] KML upload
- [x] ZIP Shapefile upload
- [x] Feature ID/index
- [x] Geometry type
- [x] Geometry
- [x] CRS
- [x] Properties/attributes
- [x] Polygon/MultiPolygon area
- [x] LineString/MultiLineString length
- [x] Point no-measurement handling
- [x] Projected CRS used for measurements
- [x] `POST /api/files/`
- [x] `GET /api/files/{id}/`
- [x] `GET /api/files/{id}/measurements/`
- [x] Error handling
- [x] Automated tests
- [x] Architecture explanation
- [x] Design decisions
- [x] Learning section
- [x] Future scope
- [x] Docker support

The remaining submission step is to push the project to a public GitHub repository and share the repository link.
