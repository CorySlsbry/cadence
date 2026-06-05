"""Integration tests for the FastAPI local sidecar."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from cadence.api.server import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(workspace=str(tmp_path / "ws"))
    return TestClient(app)


def test_health_and_capabilities(client):
    assert client.get("/health").json()["status"] == "ok"
    caps = client.get("/capabilities").json()
    assert "libx264" in caps["video_encoders"]
    assert set(caps["ml"]) == {"faster_whisper", "sentence_transformers"}


def test_brand_board_crud_over_http(client, logo_png):
    board = client.post("/brand/boards", json={"name": "Acme"}).json()
    bid = board["id"]
    assert client.get("/brand/boards").json()[0]["id"] == bid

    with open(logo_png, "rb") as fh:
        resp = client.post(
            f"/brand/boards/{bid}/assets",
            files={"file": ("logo.png", fh, "image/png")},
            data={"kind": "watermark", "anchor": "bottom_right", "opacity": "0.7", "scale": "0.18"},
        )
    assert resp.status_code == 200

    styled = client.put(
        f"/brand/boards/{bid}/caption-style",
        json={"primary_hex": "#FFEB3B", "outline_hex": "#0A0A0A"},
    ).json()
    assert styled["caption_primary"] == "#FFEB3B"

    fetched = client.get(f"/brand/boards/{bid}").json()
    assert len(fetched["assets"]) == 1
    assert client.delete(f"/brand/boards/{bid}").json()["deleted"] == bid


@pytest.mark.integration
def test_analyze_endpoint(client, reference_video):
    with open(reference_video, "rb") as fh:
        resp = client.post("/analyze", files={"reference": ("ref.mp4", fh, "video/mp4")})
    assert resp.status_code == 200
    analysis = resp.json()["analysis"]
    assert analysis["media"]["width"] == 216
    assert len(analysis["transitions"]) >= 2


@pytest.mark.integration
@pytest.mark.slow
def test_synthesize_and_download(client, talking_clip, reference_video, logo_png):
    # Brand board with a watermark.
    bid = client.post("/brand/boards", json={"name": "X"}).json()["id"]
    with open(logo_png, "rb") as fh:
        client.post(
            f"/brand/boards/{bid}/assets",
            files={"file": ("logo.png", fh, "image/png")},
            data={"kind": "watermark", "anchor": "bottom_right"},
        )
    transcript = {"language": "en", "words": [
        {"text": "hello", "start": 0.2, "end": 0.6},
        {"text": "world", "start": 2.0, "end": 2.5},
        {"text": "again", "start": 4.0, "end": 4.5},
    ]}
    with open(talking_clip, "rb") as rec, open(reference_video, "rb") as ref:
        resp = client.post(
            "/synthesize",
            files={
                "recording": ("aroll.mp4", rec, "video/mp4"),
                "reference": ("ref.mp4", ref, "video/mp4"),
            },
            data={"transcript_json": json.dumps(transcript), "board_id": bid},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result"]["width"] == 1080 and body["result"]["height"] == 1920

    dl = client.get(body["download_url"])
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "video/mp4"
    assert len(dl.content) > 1000


def test_malformed_inputs_return_4xx_not_500(client, logo_png):
    # /render with a clip missing 'source' -> 422 (not 500).
    bad = client.post("/render", json={"plan": {"clips": [{"in_point": 0, "out_point": 1}]}})
    assert bad.status_code == 422, bad.text

    bid = client.post("/brand/boards", json={"name": "X"}).json()["id"]

    # Invalid hex color -> 422.
    palette = client.post(f"/brand/boards/{bid}/palette", json={"name": "p", "colors": ["nothex"]})
    assert palette.status_code == 422

    # Invalid asset enum -> 422.
    with open(logo_png, "rb") as fh:
        asset = client.post(
            f"/brand/boards/{bid}/assets",
            files={"file": ("logo.png", fh, "image/png")},
            data={"kind": "banner"},  # not a valid AssetKind
        )
    assert asset.status_code == 422

    # Unknown board -> 404.
    assert client.get("/brand/boards/deadbeef").status_code == 404


def test_download_rejects_path_traversal_and_bad_ids(client):
    # Non-hex / traversal-shaped ids must 404, never 200 or 500.
    assert client.get("/download/" + "z" * 32).status_code == 404
    assert client.get("/download/abc").status_code == 404
    assert client.get("/download/..%5C..%5Csecret").status_code == 404


@pytest.mark.integration
@pytest.mark.slow
def test_render_endpoint_from_plan(client, talking_clip):
    plan = {
        "output": {"width": 1080, "height": 1920, "fps": 60},
        "clips": [{"source": talking_clip, "in_point": 0.0, "out_point": 2.0, "zoom": 1.0}],
        "captions": [],
        "color_grade": {"brightness": 0.0, "contrast": 1.05, "saturation": 1.1, "gamma": 1.0, "temperature": 0.0},
        "watermark": None,
        "caption_primary_hex": "#FFFFFF",
        "caption_outline_hex": "#000000",
        "audio_normalize": True,
    }
    resp = client.post("/render", json={"plan": plan})
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"]["width"] == 1080
