import os
import threading
import time
import uuid
import ssl
import certifi
import shutil
from PIL import Image
import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from geopy.geocoders import Nominatim

from create_map_poster import (
    create_poster,
    generate_output_filename,
    get_available_themes,
    get_coordinates,
    load_theme,
)

POSTERS_DIR = "posters"
EXAMPLES_DIR = "examples"
TRASH_DIR = "trashcan"

os.makedirs(POSTERS_DIR, exist_ok=True)
os.makedirs(EXAMPLES_DIR, exist_ok=True)
os.makedirs(TRASH_DIR, exist_ok=True)

app = FastAPI(title="Map Poster Studio")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/posters", StaticFiles(directory=POSTERS_DIR), name="posters")
app.mount("/examples", StaticFiles(directory=EXAMPLES_DIR), name="examples")
app.mount("/trashcan", StaticFiles(directory=TRASH_DIR), name="trashcan")

_jobs = {}
_jobs_lock = threading.Lock()
JOB_TTL_SECONDS = 6 * 60 * 60


def _prune_jobs(now_ts):
    stale = [job_id for job_id, payload in _jobs.items() if now_ts - payload.get("updated_at", now_ts) > JOB_TTL_SECONDS]
    for job_id in stale:
        _jobs.pop(job_id, None)


def _set_job(job_id, payload):
    with _jobs_lock:
        now_ts = time.time()
        _prune_jobs(now_ts)
        _jobs[job_id] = {**payload, "updated_at": now_ts}


def _update_job(job_id, updates):
    with _jobs_lock:
        now_ts = time.time()
        _prune_jobs(now_ts)
        _jobs[job_id] = {**_jobs.get(job_id, {}), **updates, "updated_at": now_ts}


def _get_job(job_id):
    with _jobs_lock:
        _prune_jobs(time.time())
    return _jobs.get(job_id)


def _get_png_metadata(path):
    try:
        with Image.open(path) as img:
            info = img.info or {}
    except Exception:
        return {}

    keys = [
        "Title",
        "City",
        "Country",
        "Theme",
        "DistanceMeters",
        "Latitude",
        "Longitude",
        "GeneratedAt",
    ]
    return {key: info.get(key, "") for key in keys if info.get(key)}


def _list_examples(themes):
    examples = []
    for theme_name in themes:
        filename = f"racksta_1000m_{theme_name}.png"
        examples.append(
            {
                "theme": theme_name,
                "filename": filename,
                "path": f"/examples/{filename}",
            }
        )
    return examples


def _list_posters(folder, url_prefix):
    posters = []
    for filename in sorted(os.listdir(folder)):
        if not filename.lower().endswith(".png"):
            continue
        path = os.path.join(folder, filename)
        meta = _get_png_metadata(path)
        posters.append(
            {
                "filename": filename,
                "path": f"{url_prefix}/{filename}",
                "meta": meta,
            }
        )
    return posters


def _render_index(request, themes, values=None, result=None, error=None):
    examples = _list_examples(themes)
    posters = _list_posters(POSTERS_DIR, "/posters")
    trash = _list_posters(TRASH_DIR, "/trashcan")
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "themes": themes,
            "examples": examples,
            "posters": posters,
            "trash": trash,
            "values": values or {},
            "result": result,
            "error": error,
        },
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    themes = get_available_themes()
    defaults = {
        "city": "",
        "country": "",
        "theme": "feature_based",
        "distance": 29000,
    }
    return _render_index(request, themes, values=defaults)


@app.post("/generate", response_class=HTMLResponse)
def generate(
    request: Request,
    city: str = Form(...),
    country: str = Form(...),
    theme: str = Form("feature_based"),
    distance: int = Form(29000),
):
    themes = get_available_themes()
    values = {
        "city": city.strip(),
        "country": country.strip(),
        "theme": theme,
        "distance": distance,
    }

    if not values["city"] or not values["country"]:
        return _render_index(request, themes, values=values, error="City and country are required.")

    if theme not in themes:
        return _render_index(request, themes, values=values, error="Theme not found.")

    if distance <= 0:
        return _render_index(request, themes, values=values, error="Distance must be positive.")

    try:
        theme_data = load_theme(theme)
        coords = get_coordinates(values["city"], values["country"])
        output_file = generate_output_filename(values["city"], theme)
        create_poster(
            values["city"],
            values["country"],
            coords,
            distance,
            output_file,
            theme_data,
            show_progress=False,
        )
    except Exception as exc:
        return _render_index(request, themes, values=values, error=str(exc))

    result = {
        "filename": os.path.basename(output_file),
        "path": f"/posters/{os.path.basename(output_file)}",
    }
    return _render_index(request, themes, values=values, result=result)


def _run_job(job_id, values):
    _update_job(job_id, {"status": "running"})
    try:
        theme_data = load_theme(values["theme"])
        coords = get_coordinates(values["city"], values["country"])
        output_file = generate_output_filename(values["city"], values["theme"])
        create_poster(
            values["city"],
            values["country"],
            coords,
            values["distance"],
            output_file,
            theme_data,
            show_progress=False,
        )
    except Exception as exc:
        _update_job(job_id, {"status": "error", "error": str(exc)})
        return

    _update_job(
        job_id,
        {
            "status": "done",
            "filename": os.path.basename(output_file),
            "path": f"/posters/{os.path.basename(output_file)}",
        },
    )


@app.post("/api/generate")
def generate_api(
    city: str = Form(...),
    country: str = Form(...),
    theme: str = Form("feature_based"),
    distance: int = Form(29000),
):
    themes = get_available_themes()
    values = {
        "city": city.strip(),
        "country": country.strip(),
        "theme": theme,
        "distance": distance,
    }

    if not values["city"] or not values["country"]:
        return {"status": "error", "error": "City and country are required."}

    if theme not in themes:
        return {"status": "error", "error": "Theme not found."}

    if distance <= 0:
        return {"status": "error", "error": "Distance must be positive."}

    job_id = uuid.uuid4().hex
    _set_job(job_id, {"status": "queued"})
    threading.Thread(target=_run_job, args=(job_id, values), daemon=True).start()
    return {"status": "queued", "job_id": job_id}


@app.get("/api/status/{job_id}")
def status_api(job_id: str):
    job = _get_job(job_id)
    if not job:
        return {"status": "error", "error": "Job not found."}
    return {"status": job.get("status"), **job}


@app.get("/api/geocode")
def geocode_api(query: str = "", country: str = ""):
    query = query.strip()
    country = country.strip()

    if not query:
        return {"status": "error", "error": "Enter a city or address to search."}

    query_parts = [part for part in [query, country] if part]
    query = ", ".join(query_parts)

    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        geolocator = Nominatim(user_agent="city_map_poster_webui", ssl_context=ssl_context)
        time.sleep(1)
        location = geolocator.geocode(query)
        if not location:
            raise ValueError("Location not found.")
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    return {"status": "ok", "lat": location.latitude, "lon": location.longitude}


def delete_poster_api(filename: str):
    safe_name = os.path.basename(filename)
    if not safe_name.lower().endswith(".png"):
        return {"status": "error", "error": "Invalid filename."}

    source_path = os.path.join(POSTERS_DIR, safe_name)
    if not os.path.exists(source_path):
        return {"status": "error", "error": "Poster not found."}

    trash_path = os.path.join(TRASH_DIR, safe_name)
    if os.path.exists(trash_path):
        stem, ext = os.path.splitext(safe_name)
        trash_path = os.path.join(TRASH_DIR, f"{stem}_{int(time.time())}{ext}")
    shutil.move(source_path, trash_path)
    return {"status": "ok", "filename": os.path.basename(trash_path)}


@app.post("/api/posters/delete")
def delete_poster(filename: str = Form(...)):
    return delete_poster_api(filename)


def restore_poster_api(filename: str):
    safe_name = os.path.basename(filename)
    if not safe_name.lower().endswith(".png"):
        return {"status": "error", "error": "Invalid filename."}

    source_path = os.path.join(TRASH_DIR, safe_name)
    if not os.path.exists(source_path):
        return {"status": "error", "error": "Poster not found."}

    target_path = os.path.join(POSTERS_DIR, safe_name)
    if os.path.exists(target_path):
        stem, ext = os.path.splitext(safe_name)
        target_path = os.path.join(POSTERS_DIR, f"{stem}_{int(time.time())}{ext}")
    shutil.move(source_path, target_path)
    return {"status": "ok", "filename": os.path.basename(target_path)}


@app.post("/api/posters/restore")
def restore_poster(filename: str = Form(...)):
    return restore_poster_api(filename)


def purge_poster_api(filename: str):
    safe_name = os.path.basename(filename)
    if not safe_name.lower().endswith(".png"):
        return {"status": "error", "error": "Invalid filename."}

    source_path = os.path.join(TRASH_DIR, safe_name)
    if not os.path.exists(source_path):
        return {"status": "error", "error": "Poster not found."}

    os.remove(source_path)
    return {"status": "ok", "filename": safe_name}


@app.post("/api/posters/purge")
def purge_poster(filename: str = Form(...)):
    return purge_poster_api(filename)


@strawberry.type
class Meta:
    Title: str | None = None
    City: str | None = None
    Country: str | None = None
    Theme: str | None = None
    DistanceMeters: str | None = None
    Latitude: str | None = None
    Longitude: str | None = None
    GeneratedAt: str | None = None


@strawberry.type
class FileItem:
    filename: str
    path: str
    theme: str | None = None
    meta: Meta | None = None


@strawberry.type
class JobStatus:
    status: str
    job_id: str | None = None
    filename: str | None = None
    path: str | None = None
    error: str | None = None


@strawberry.type
class GeocodeResult:
    status: str
    lat: float | None = None
    lon: float | None = None
    error: str | None = None


def _meta_from_dict(data):
    if not data:
        return None
    return Meta(**data)


@strawberry.type
class Query:
    @strawberry.field
    def themes(self) -> list[str]:
        return get_available_themes()

    @strawberry.field
    def examples(self) -> list[FileItem]:
        examples = _list_examples(get_available_themes())
        return [
            FileItem(
                filename=item["filename"],
                path=item["path"],
                theme=item["theme"],
                meta=None,
            )
            for item in examples
        ]

    @strawberry.field
    def posters(self) -> list[FileItem]:
        posters = _list_posters(POSTERS_DIR, "/posters")
        return [
            FileItem(
                filename=item["filename"],
                path=item["path"],
                theme=None,
                meta=_meta_from_dict(item.get("meta")),
            )
            for item in posters
        ]

    @strawberry.field
    def trash(self) -> list[FileItem]:
        trash = _list_posters(TRASH_DIR, "/trashcan")
        return [
            FileItem(
                filename=item["filename"],
                path=item["path"],
                theme=None,
                meta=_meta_from_dict(item.get("meta")),
            )
            for item in trash
        ]

    @strawberry.field
    def job(self, job_id: str) -> JobStatus:
        job = _get_job(job_id)
        if not job:
            return JobStatus(status="error", error="Job not found.")
        return JobStatus(
            status=job.get("status"),
            job_id=job_id,
            filename=job.get("filename"),
            path=job.get("path"),
            error=job.get("error"),
        )


@strawberry.type
class Mutation:
    @strawberry.mutation
    def geocode(self, query: str, country: str = "") -> GeocodeResult:
        result = geocode_api(query=query, country=country)
        return GeocodeResult(**result)

    @strawberry.mutation
    def generate(self, city: str, country: str, theme: str = "feature_based", distance: int = 29000) -> JobStatus:
        result = generate_api(city=city, country=country, theme=theme, distance=distance)
        return JobStatus(
            status=result.get("status"),
            job_id=result.get("job_id"),
            error=result.get("error"),
        )

    @strawberry.mutation
    def delete_poster(self, filename: str) -> JobStatus:
        result = delete_poster_api(filename)
        return JobStatus(status=result.get("status"), filename=result.get("filename"), error=result.get("error"))

    @strawberry.mutation
    def restore_poster(self, filename: str) -> JobStatus:
        result = restore_poster_api(filename)
        return JobStatus(status=result.get("status"), filename=result.get("filename"), error=result.get("error"))

    @strawberry.mutation
    def purge_poster(self, filename: str) -> JobStatus:
        result = purge_poster_api(filename)
        return JobStatus(status=result.get("status"), filename=result.get("filename"), error=result.get("error"))


schema = strawberry.Schema(query=Query, mutation=Mutation)
app.include_router(GraphQLRouter(schema), prefix="/graphql")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("webui:app", host="0.0.0.0", port=8000, reload=True)
