from fastapi import FastAPI

from api.routers import health, runs, sources

app = FastAPI(title="IURISYNC Backend")
app.include_router(health.router)
app.include_router(sources.router)
app.include_router(runs.router)
