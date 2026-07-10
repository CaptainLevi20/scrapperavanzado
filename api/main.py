from fastapi import FastAPI

from api.routers import health

app = FastAPI(title="IURISYNC Backend")
app.include_router(health.router)
