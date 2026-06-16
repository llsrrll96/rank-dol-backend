from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .crawling.routes import router as crawling_router
from .idols.routes import router as idols_router
from .tier_lists.routes import router as tier_lists_router
from .auth.routes import router as auth_router
from .users.routes import router as users_router

app = FastAPI(
    title="Idol Crawler API",
    description="API for crawling idol group data and saving to Supabase",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(crawling_router)
app.include_router(idols_router)
app.include_router(tier_lists_router)
app.include_router(auth_router)
app.include_router(users_router)

@app.get("/")
def read_root():
    return {"message": "Idol Crawler API is running"}
