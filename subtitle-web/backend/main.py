# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from routes.translate import router as translate_router
from routes.presets import router as presets_router

app = FastAPI(
    title="字幕翻译 API",
    description="基于 FastAPI 的字幕翻译服务，支持 SRT/MKV/ASS 文件翻译",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 确保所有路由都在 /api 前缀下，即使 router 本身带了前缀，FastAPI 也会自动处理。
app.include_router(translate_router)
app.include_router(presets_router)


@app.get("/")
async def root():
    return {"message": "字幕翻译 API", "version": "1.0.0", "docs": "/docs"}


@app.get("/api/health")
async def api_health():
    return {"status": "ok", "message": "API is reachable"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8273)

