from fastapi import FastAPI

from api.routers import documents, health, runs, sources

app = FastAPI(title="IURISYNC Backend")
app.include_router(health.router)
app.include_router(sources.router)
app.include_router(runs.router)
app.include_router(documents.router)
