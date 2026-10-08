const fileInput = document.getElementById("fileInput"),
  dropZone = document.getElementById("dropZone"),
  uploadBtn = document.getElementById("uploadBtn"),
  selectedFileBox = document.getElementById("selectedFile"),
  fileName = document.getElementById("fileName"),
  fileSize = document.getElementById("fileSize"),
  removeFileBtn = document.getElementById("removeFile"),
  statusBox = document.getElementById("statusBox"),
  statusText = document.getElementById("statusText"),
  resultsSection = document.getElementById("resultsSection"),
  errorBox = document.getElementById("errorBox"),
  errorText = document.getElementById("errorText");
let selectedFile = null;
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) handleFile(fileInput.files[0]);
});
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});
dropZone.addEventListener("dragleave", () =>
  dropZone.classList.remove("dragover"),
);
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
function handleFile(file) {
  hideError();
  const name = file.name.toLowerCase();
  if (!name.endsWith(".kml") && !name.endsWith(".zip")) {
    showError(
      "Unsupported file type. Upload a .kml or .zip Shapefile archive.",
    );
    return;
  }
  if (file.size > 50 * 1024 * 1024) {
    showError("File exceeds the 50 MB upload limit.");
    return;
  }
  selectedFile = file;
  fileName.textContent = file.name;
  fileSize.textContent = formatFileSize(file.size);
  selectedFileBox.classList.remove("hidden");
  uploadBtn.disabled = false;
}
removeFileBtn.addEventListener("click", () => {
  selectedFile = null;
  fileInput.value = "";
  selectedFileBox.classList.add("hidden");
  uploadBtn.disabled = true;
});
uploadBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  hideError();
  resultsSection.classList.add("hidden");
  uploadBtn.disabled = true;
  statusBox.classList.remove("hidden");
  statusText.textContent = "Uploading and processing file...";
  const form = new FormData();
  form.append("file", selectedFile);
  try {
    const response = await fetch("/api/files/", { method: "POST", body: form });
    const data = await parseResponse(response);
    if (!response.ok)
      throw new Error(
        data.detail || data.message || "Unable to process the file.",
      );
    const id = data.id;
    if (!id) throw new Error("Upload succeeded but no file ID was returned.");
    statusText.textContent = "Loading feature measurements...";
    const [info, measurementData] = await Promise.all([
      getFileInfo(id),
      getMeasurements(id),
    ]);
    displayResults(info, measurementData);
  } catch (error) {
    console.error(error);
    showError(error.message);
    statusBox.classList.add("hidden");
  } finally {
    uploadBtn.disabled = false;
  }
});
async function getFileInfo(id) {
  const r = await fetch(`/api/files/${encodeURIComponent(id)}/`),
    d = await parseResponse(r);
  if (!r.ok)
    throw new Error(d.detail || "Unable to retrieve file information.");
  return d;
}
async function getMeasurements(id) {
  const r = await fetch(`/api/files/${encodeURIComponent(id)}/measurements/`),
    d = await parseResponse(r);
  if (!r.ok) throw new Error(d.detail || "Unable to retrieve measurements.");
  return d;
}
function displayResults(info, data) {
  statusBox.classList.add("hidden");
  resultsSection.classList.remove("hidden");
  document.getElementById("resultFilename").textContent = info.filename || "—";
  document.getElementById("featureCount").textContent =
    info.feature_count ?? "—";
  document.getElementById("resultCrs").textContent = info.crs || "—";
  document.getElementById("measurementCrs").textContent =
    info.measurement_crs || "Not required";
  document.getElementById("statusBadge").textContent =
    info.status || "COMPLETED";
  const rows = Array.isArray(data.measurements) ? data.measurements : [];
  const featureMap = new Map(
    (data.features || []).map((f) => [String(f.feature_id), f]),
  );
  const body = document.getElementById("measurementsBody");
  body.innerHTML = "";
  document.getElementById("measurementCount").textContent =
    `${rows.length} feature${rows.length === 1 ? "" : "s"}`;
  document
    .getElementById("emptyMeasurements")
    .classList.toggle("hidden", rows.length > 0);
  rows.forEach((m, i) => {
    const f = featureMap.get(String(m.feature_id)) || {};
    const tr = document.createElement("tr");
    const props = f.properties || {};
    tr.innerHTML = `<td>${i + 1}</td><td><span class="geometry-pill">${escapeHtml(m.geometry_type || f.geometry_type || "Unknown")}</span></td><td>${escapeHtml(m.measurement_type || "None")}</td><td class="measurement-value">${formatMeasurement(m.measurement, m.unit)}</td><td><div class="properties" title="${escapeHtml(JSON.stringify(props))}">${escapeHtml(JSON.stringify(props))}</div></td>`;
    body.appendChild(tr);
  });
}
function formatMeasurement(value, unit) {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return escapeHtml(String(value));
  return `${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ""}`;
}
function formatFileSize(bytes) {
  if (bytes === 0) return "0 Bytes";
  const units = ["Bytes", "KB", "MB", "GB"],
    i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${parseFloat((bytes / Math.pow(1024, i)).toFixed(2))} ${units[i]}`;
}
async function parseResponse(r) {
  const t = await r.text();
  if (!t) return {};
  try {
    return JSON.parse(t);
  } catch {
    return { message: t };
  }
}
function showError(message) {
  errorText.textContent = message;
  errorBox.classList.remove("hidden");
}
function hideError() {
  errorBox.classList.add("hidden");
  errorText.textContent = "";
}
function escapeHtml(v) {
  return String(v)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
