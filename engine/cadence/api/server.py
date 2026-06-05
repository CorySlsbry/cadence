"""FastAPI local sidecar exposing the Cadence engine to the Flutter client.

Designed as a LOCALHOST daemon co-located with the app, so file paths in
request/response bodies are valid on both sides. Uploaded media is persisted to a
workspace; renders land in a jobs directory and are streamed back via /download.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from cadence import analyze_reference, build_generation_plan, clean_recording, render_plan
from cadence.brandboard.store import BrandBoardStore
from cadence.config import CleaningConfig, EngineConfig
from cadence.errors import BrandBoardError, CadenceError
from cadence.ffmpeg.runner import FFmpeg

_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
from cadence.models import (
    Anchor,
    AssetKind,
    BrandPalette,
    GenerationPlan,
    RGBColor,
    Transcript,
)


class BoardCreate(BaseModel):
    name: str


class CaptionStyle(BaseModel):
    primary_hex: str | None = None
    outline_hex: str | None = None
    font_path: str | None = None


class PaletteIn(BaseModel):
    name: str
    colors: list[str]


class RenderRequest(BaseModel):
    plan: dict


def _ml_available(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


def create_app(workspace: str = "cadence_workspace") -> FastAPI:
    os.makedirs(workspace, exist_ok=True)
    uploads = os.path.join(workspace, "uploads")
    jobs = os.path.join(workspace, "jobs")
    os.makedirs(uploads, exist_ok=True)
    os.makedirs(jobs, exist_ok=True)
    brand_db = os.path.join(workspace, "brand.db")

    cfg = EngineConfig()
    ff = FFmpeg(cfg.ffmpeg_bin, cfg.ffprobe_bin)
    app = FastAPI(title="Cadence Engine", version="1.0.0")

    # Centralized input-error translation: a missing brand board is a 404, any other
    # engine error or malformed-input ValueError is a clean 422 (never a raw 500).
    @app.exception_handler(CadenceError)
    async def _cadence_error(_request: Request, exc: CadenceError) -> JSONResponse:
        status = 404 if isinstance(exc, BrandBoardError) else 422
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": f"invalid request: {exc}"})

    def _save_upload(up: UploadFile, subdir: str = "") -> str:
        target_dir = os.path.join(uploads, subdir) if subdir else uploads
        os.makedirs(target_dir, exist_ok=True)
        ext = os.path.splitext(up.filename or "")[1] or ".bin"
        path = os.path.join(target_dir, f"{uuid.uuid4().hex}{ext}")
        with open(path, "wb") as fh:
            shutil.copyfileobj(up.file, fh)
        return path

    def _store() -> BrandBoardStore:
        return BrandBoardStore(brand_db)

    # -- meta --------------------------------------------------------------- #
    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": app.version}

    @app.get("/capabilities")
    def capabilities() -> dict:
        encs = sorted(e for e in ff.available_encoders() if "264" in e or "nvenc" in e or "amf" in e or "qsv" in e)
        return {
            "ffmpeg": ff.ffmpeg_bin,
            "video_encoders": encs,
            "ml": {
                "faster_whisper": _ml_available("faster_whisper"),
                "sentence_transformers": _ml_available("sentence_transformers"),
            },
        }

    # -- pipeline ----------------------------------------------------------- #
    @app.post("/analyze")
    async def analyze(reference: UploadFile = File(...)) -> dict:
        path = _save_upload(reference)
        try:
            analysis = analyze_reference(path, ff=ff)
        except CadenceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"source_path": path, "analysis": analysis.to_dict()}

    @app.post("/clean")
    async def clean(
        recording: UploadFile = File(...),
        transcript_json: str | None = Form(None),
        aggressive_fillers: bool = Form(False),
    ) -> dict:
        path = _save_upload(recording)
        transcript = _parse_transcript(transcript_json)
        clean_cfg = CleaningConfig(aggressive_fillers=aggressive_fillers)
        try:
            edl = clean_recording(path, transcript=transcript, cfg=clean_cfg, ff=ff)
        except CadenceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"source_path": path, "edl": edl.to_dict()}

    @app.post("/synthesize")
    async def synthesize(
        recording: UploadFile = File(...),
        reference: UploadFile | None = File(None),
        transcript_json: str | None = Form(None),
        board_id: str | None = Form(None),
        aggressive_fillers: bool = Form(False),
    ) -> dict:
        rec_path = _save_upload(recording)
        transcript = _parse_transcript(transcript_json)
        analysis = None
        if reference is not None:
            analysis = analyze_reference(_save_upload(reference), ff=ff)
        brand = None
        if board_id:
            with _store() as store:
                brand = store.get_board(board_id)
        try:
            edl = clean_recording(
                rec_path, transcript=transcript,
                cfg=CleaningConfig(aggressive_fillers=aggressive_fillers), ff=ff,
            )
            plan = build_generation_plan(edl, analysis=analysis, brand=brand)
            job_id = uuid.uuid4().hex
            out_path = os.path.join(jobs, f"{job_id}.mp4")
            result = render_plan(plan, out_path, ff=ff)
        except CadenceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "job_id": job_id,
            "download_url": f"/download/{job_id}",
            "edl": edl.to_dict(),
            "plan": plan.to_dict(),
            "result": result.to_dict(),
        }

    @app.post("/render")
    def render(req: RenderRequest) -> dict:
        try:
            plan = GenerationPlan.from_dict(req.plan)
            job_id = uuid.uuid4().hex
            out_path = os.path.join(jobs, f"{job_id}.mp4")
            result = render_plan(plan, out_path, ff=ff)
        except CadenceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"job_id": job_id, "download_url": f"/download/{job_id}", "result": result.to_dict()}

    @app.get("/download/{job_id}")
    def download(job_id: str) -> FileResponse:
        # job_id is always a uuid4 hex; reject anything else so a crafted value
        # (e.g. URL-encoded "..\..\secret") cannot escape the jobs directory.
        if not _JOB_ID_RE.match(job_id):
            raise HTTPException(status_code=404, detail="job output not found")
        path = os.path.join(jobs, f"{job_id}.mp4")
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="job output not found")
        return FileResponse(path, media_type="video/mp4", filename=f"{job_id}.mp4")

    # -- brand board -------------------------------------------------------- #
    @app.post("/brand/boards")
    def create_board(body: BoardCreate) -> dict:
        with _store() as store:
            return store.create_board(body.name).to_dict()

    @app.get("/brand/boards")
    def list_boards() -> list[dict]:
        with _store() as store:
            return [b.to_dict() for b in store.list_boards()]

    @app.get("/brand/boards/{board_id}")
    def get_board(board_id: str) -> dict:
        try:
            with _store() as store:
                return store.get_board(board_id).to_dict()
        except CadenceError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/brand/boards/{board_id}")
    def delete_board(board_id: str) -> dict:
        with _store() as store:
            store.delete_board(board_id)
        return {"deleted": board_id}

    @app.post("/brand/boards/{board_id}/palette")
    def add_palette(board_id: str, body: PaletteIn) -> dict:
        try:
            with _store() as store:
                palette = BrandPalette(name=body.name, colors=[RGBColor.from_hex(c) for c in body.colors])
                return store.add_palette(board_id, palette).to_dict()
        except CadenceError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/brand/boards/{board_id}/assets")
    async def add_asset(
        board_id: str,
        file: UploadFile = File(...),
        kind: str = Form("watermark"),
        anchor: str = Form("bottom_right"),
        opacity: float = Form(1.0),
        scale: float = Form(0.18),
        name: str = Form("asset"),
    ) -> dict:
        # Validate enums BEFORE persisting the upload so a bad request leaves no
        # orphaned file on disk (ValueError -> 422 via the app handler).
        asset_kind = AssetKind(kind)
        asset_anchor = Anchor(anchor)
        path = _save_upload(file, subdir="brand")
        with _store() as store:
            asset = store.add_asset(
                board_id, kind=asset_kind, name=name, path=path,
                opacity=opacity, anchor=asset_anchor, scale=scale,
            )
            return asset.to_dict()

    @app.put("/brand/boards/{board_id}/caption-style")
    def set_caption_style(board_id: str, body: CaptionStyle) -> dict:
        try:
            with _store() as store:
                return store.set_caption_style(
                    board_id,
                    font_path=body.font_path,
                    primary=RGBColor.from_hex(body.primary_hex) if body.primary_hex else None,
                    outline=RGBColor.from_hex(body.outline_hex) if body.outline_hex else None,
                ).to_dict()
        except CadenceError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


def _parse_transcript(transcript_json: str | None) -> Transcript | None:
    if not transcript_json:
        return None
    import json

    return Transcript.from_dict(json.loads(transcript_json))


# Module-level app for `uvicorn cadence.api.server:app`.
app = create_app()


def serve(host: str = "127.0.0.1", port: int = 8765, workspace: str = "cadence_workspace") -> None:
    import uvicorn

    uvicorn.run(create_app(workspace), host=host, port=port)
