import os
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services.douyin_login import LoginManager
from services.download_service import download_video, parse_video_info
from services.download_tasks import DownloadTaskManager


API_TOKEN = os.environ.get("DOUYIN_PARSE_API_TOKEN", "")

app = FastAPI(title="Douyin Parse Local API", version="1.0.0")
login_manager = LoginManager()
download_task_manager = DownloadTaskManager()
WEB_INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "index.html")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthSessionRequest(BaseModel):
    qr_timeout: int = Field(default=30, ge=1, le=60)


class DownloadVideoRequest(BaseModel):
    url: str = Field(min_length=1)
    session_id: str | None = None
    quality: str | None = None


class ParseVideoRequest(BaseModel):
    url: str = Field(min_length=1)
    session_id: str | None = None


def verify_api_token(x_api_token: Annotated[str | None, Header()] = None) -> None:
    if API_TOKEN and x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="无效的本地 API Token")


@app.get("/")
def index():
    return FileResponse(WEB_INDEX)


@app.get("/health", dependencies=[Depends(verify_api_token)])
def health() -> dict:
    return {
        "status": "ok",
        "has_cookie": bool(login_manager.get_cookie()),
        "auth_required": bool(API_TOKEN),
    }


@app.post("/auth/session", dependencies=[Depends(verify_api_token)])
def create_auth_session(payload: AuthSessionRequest) -> dict:
    session = login_manager.create_session(qr_timeout=payload.qr_timeout)
    snapshot = session.snapshot(include_qr=True)
    if snapshot["status"] == "failed":
        raise HTTPException(status_code=500, detail=snapshot.get("message", "创建扫码会话失败"))
    return snapshot


@app.get("/auth/session/{session_id}", dependencies=[Depends(verify_api_token)])
def get_auth_session(session_id: str) -> dict:
    session = login_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="扫码会话不存在")
    return session.snapshot(include_qr=True)


@app.post("/parse/video", dependencies=[Depends(verify_api_token)])
def parse_video_api(payload: ParseVideoRequest) -> dict:
    cookie = login_manager.get_cookie(payload.session_id)
    if not cookie:
        raise HTTPException(status_code=401, detail="请先调用 /auth/session 扫码登录")

    try:
        return parse_video_info(payload.url, cookie=cookie)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/download/video", dependencies=[Depends(verify_api_token)])
def download_video_api(payload: DownloadVideoRequest):
    cookie = login_manager.get_cookie(payload.session_id)
    if not cookie:
        raise HTTPException(status_code=401, detail="请先调用 /auth/session 扫码登录")

    try:
        result = download_video(payload.url, cookie=cookie, quality=payload.quality)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileResponse(
        result.path,
        media_type=result.content_type,
        filename=result.filename,
    )


@app.post("/download/video/task", dependencies=[Depends(verify_api_token)])
def create_download_video_task(payload: DownloadVideoRequest) -> dict:
    cookie = login_manager.get_cookie(payload.session_id)
    if not cookie:
        raise HTTPException(status_code=401, detail="请先调用 /auth/session 扫码登录")

    task = download_task_manager.create_task(
        payload.url,
        cookie=cookie,
        quality=payload.quality,
    )
    return task.snapshot()


@app.get("/download/video/task/{task_id}", dependencies=[Depends(verify_api_token)])
def get_download_video_task(task_id: str) -> dict:
    task = download_task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="下载任务不存在")
    return task.snapshot()


@app.get("/download/video/task/{task_id}/file", dependencies=[Depends(verify_api_token)])
def get_download_video_task_file(task_id: str):
    task = download_task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="下载任务不存在")
    if task.status != "done" or not task.result:
        raise HTTPException(status_code=409, detail="下载任务尚未完成")

    return FileResponse(
        task.result.path,
        media_type=task.result.content_type,
        filename=task.result.filename,
    )
