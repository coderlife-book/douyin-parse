from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app_meta import APP_VERSION
from runtime_paths import model_path, web_index_path
from services.douyin_login import LoginManager, clear_cookie
from services.download_service import download_video, parse_video_info, open_video_stream
from services.download_tasks import DownloadTaskManager
from services.transcription_tasks import TranscriptionTaskManager


app = FastAPI(title="Douyin Parse Local API", version=APP_VERSION)
login_manager = LoginManager()
download_task_manager = DownloadTaskManager()
transcription_task_manager = TranscriptionTaskManager()
WEB_INDEX = str(web_index_path())

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
def shutdown_transcription_tasks() -> None:
    transcription_task_manager.close(wait=False)


class AuthSessionRequest(BaseModel):
    qr_timeout: int = Field(default=30, ge=1, le=60)


class DownloadVideoRequest(BaseModel):
    url: str = Field(min_length=1)
    session_id: str | None = None
    quality: str | None = None


class ParseVideoRequest(BaseModel):
    url: str = Field(min_length=1)
    session_id: str | None = None


class TranscriptionRequest(BaseModel):
    url: str = Field(min_length=1)
    session_id: str | None = None


@app.get("/")
def index():
    return FileResponse(WEB_INDEX)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "has_cookie": bool(login_manager.get_cookie()),
        "version": APP_VERSION,
        "asr_model_ready": model_path().is_dir(),
        "transcription_busy": transcription_task_manager.is_busy(),
    }


@app.post("/auth/session")
def create_auth_session(payload: AuthSessionRequest) -> dict:
    session = login_manager.create_session(qr_timeout=payload.qr_timeout)
    snapshot = session.snapshot(include_qr=True)
    if snapshot["status"] == "failed":
        raise HTTPException(status_code=500, detail=snapshot.get("message", "创建扫码会话失败"))
    return snapshot


@app.get("/auth/session/{session_id}")
def get_auth_session(session_id: str) -> dict:
    session = login_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="扫码会话不存在")
    return session.snapshot(include_qr=True)


@app.post("/auth/logout")
def logout() -> dict:
    clear_cookie()
    return {"status": "ok", "message": "已退出登录"}


@app.post("/parse/video")
def parse_video_api(payload: ParseVideoRequest) -> dict:
    cookie = login_manager.get_cookie(payload.session_id)
    if not cookie:
        raise HTTPException(status_code=401, detail="请先调用 /auth/session 扫码登录")

    try:
        return parse_video_info(payload.url, cookie=cookie)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/preview/video")
def preview_video(
    request: Request,
    url: str,
    quality: str | None = None,
    session_id: str | None = None,
):
    cookie = login_manager.get_cookie(session_id)
    if not cookie:
        raise HTTPException(status_code=401, detail="请先调用 /auth/session 扫码登录")

    try:
        stream, status_code, resp_headers = open_video_stream(
            url,
            cookie=cookie,
            quality=quality,
            range_header=request.headers.get("range"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StreamingResponse(
        stream,
        status_code=status_code,
        media_type="video/mp4",
        headers=resp_headers,
    )


@app.post("/download/video")
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


@app.post("/download/video/task")
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


@app.get("/download/video/task/{task_id}")
def get_download_video_task(task_id: str) -> dict:
    task = download_task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="下载任务不存在")
    return task.snapshot()


@app.get("/download/video/task/{task_id}/file")
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


@app.post("/transcription/tasks")
def create_transcription_task(payload: TranscriptionRequest) -> dict:
    cookie = login_manager.get_cookie(payload.session_id)
    if not cookie:
        raise HTTPException(status_code=401, detail="请先扫码登录抖音")
    task = transcription_task_manager.create_task(payload.url, cookie=cookie)
    return task.snapshot()


@app.get("/transcription/tasks")
def list_transcription_tasks() -> list[dict]:
    return [task.snapshot() for task in transcription_task_manager.list_tasks()]


@app.get("/transcription/tasks/{task_id}")
def get_transcription_task(task_id: str) -> dict:
    task = transcription_task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="字幕任务不存在")
    return task.snapshot(include_segments=True)


@app.get("/transcription/tasks/{task_id}/text")
def get_transcription_text(task_id: str):
    task = transcription_task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="字幕任务不存在")
    path = transcription_task_manager.text_path(task_id)
    if task.status != "done" or not path.is_file():
        raise HTTPException(status_code=409, detail="字幕任务尚未完成")
    return FileResponse(
        str(path),
        media_type="text/plain; charset=utf-8",
        filename=f"字幕-{task_id}.txt",
    )
