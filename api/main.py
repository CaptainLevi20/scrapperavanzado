from fastapi import FastAPI

from api.routers import health, sources

app = FastAPI(title="IURISYNC Backend")
app.include_router(health.router)
app.include_router(sources.router)
