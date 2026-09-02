from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import auth, bulk_downloads, cali_decretos, case_links, documents, health, reorganize, runs, sources
from core.config import get_settings

app = FastAPI(title="IURISYNC Backend")

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _settings.cors_origins.split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(sources.router)
app.include_router(runs.router)
app.include_router(documents.router)
app.include_router(bulk_downloads.router)
app.include_router(case_links.router)
app.include_router(reorganize.router)
app.include_router(cali_decretos.router)
