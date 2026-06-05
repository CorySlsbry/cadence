"""Command-line interface: cadence analyze|clean|synthesize|render|brand|serve."""

from __future__ import annotations

import argparse
import json
import sys

from cadence import analyze_reference, build_generation_plan, clean_recording, render_plan
from cadence.brandboard.store import BrandBoardStore
from cadence.config import CleaningConfig, EngineConfig, SynthesisConfig
from cadence.errors import CadenceError
from cadence.ffmpeg.runner import FFmpeg
from cadence.models import Anchor, AssetKind, GenerationPlan, RGBColor, Transcript


def _load_transcript(path: str | None) -> Transcript | None:
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        return Transcript.from_dict(json.load(fh))


def _write(obj: dict, out: str | None) -> None:
    text = json.dumps(obj, indent=2)
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {out}")
    else:
        print(text)


def cmd_analyze(args: argparse.Namespace, ff: FFmpeg) -> int:
    analysis = analyze_reference(args.video, ff=ff)
    _write(analysis.to_dict(), args.out)
    return 0


def cmd_clean(args: argparse.Namespace, ff: FFmpeg) -> int:
    cfg = CleaningConfig(aggressive_fillers=args.aggressive_fillers)
    edl = clean_recording(args.video, transcript=_load_transcript(args.transcript), cfg=cfg, ff=ff)
    _write(edl.to_dict(), args.out)
    if args.render:
        from cadence.cleaning.editor import render_edl

        res = render_edl(edl, args.render, ff=ff)
        print(f"rendered cleaned clip -> {res.output_path} ({res.duration:.2f}s)")
    return 0


def cmd_synthesize(args: argparse.Namespace, ff: FFmpeg) -> int:
    analysis = analyze_reference(args.reference, ff=ff) if args.reference else None
    brand = None
    if args.brand_db and args.board:
        with BrandBoardStore(args.brand_db) as store:
            brand = store.get_board(args.board)
    edl = clean_recording(
        args.video, transcript=_load_transcript(args.transcript),
        cfg=CleaningConfig(aggressive_fillers=args.aggressive_fillers), ff=ff,
    )
    plan = build_generation_plan(edl, analysis=analysis, brand=brand, cfg=SynthesisConfig())
    if args.plan_out:
        _write(plan.to_dict(), args.plan_out)
    res = render_plan(plan, args.out, ff=ff, log_path=args.graph_out)
    print(f"rendered -> {res.output_path}  {res.width}x{res.height}@{res.fps:.0f}fps "
          f"{res.duration:.2f}s encoder={res.encoder} hardware={res.used_hardware}")
    return 0


def cmd_render(args: argparse.Namespace, ff: FFmpeg) -> int:
    with open(args.plan, encoding="utf-8") as fh:
        plan = GenerationPlan.from_dict(json.load(fh))
    res = render_plan(plan, args.out, ff=ff)
    print(f"rendered -> {res.output_path} ({res.duration:.2f}s)")
    return 0


def cmd_brand(args: argparse.Namespace, ff: FFmpeg) -> int:
    with BrandBoardStore(args.brand_db) as store:
        if args.brand_cmd == "create":
            board = store.create_board(args.name)
            print(board.id)
        elif args.brand_cmd == "list":
            for b in store.list_boards():
                print(f"{b.id}\t{b.name}\t{len(b.assets)} assets")
        elif args.brand_cmd == "add-asset":
            asset = store.add_asset(
                args.board, kind=AssetKind(args.kind), name=args.name, path=args.path,
                opacity=args.opacity, anchor=Anchor(args.anchor), scale=args.scale,
            )
            print(asset.id)
        elif args.brand_cmd == "caption-style":
            store.set_caption_style(
                args.board,
                font_path=args.font,
                primary=RGBColor.from_hex(args.primary) if args.primary else None,
                outline=RGBColor.from_hex(args.outline) if args.outline else None,
            )
            print("updated")
    return 0


def cmd_serve(args: argparse.Namespace, ff: FFmpeg) -> int:
    from cadence.api.server import serve

    serve(host=args.host, port=args.port, workspace=args.workspace)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cadence", description="AI short-form video automation engine")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="analyze a reference video")
    a.add_argument("video")
    a.add_argument("--out", help="write analysis JSON here")
    a.set_defaults(func=cmd_analyze)

    c = sub.add_parser("clean", help="clean a raw recording -> edit decision list")
    c.add_argument("video")
    c.add_argument("--transcript", help="word-timed transcript JSON")
    c.add_argument("--out", help="write EDL JSON here")
    c.add_argument("--render", help="also render the cleaned clip to this mp4")
    c.add_argument("--aggressive-fillers", action="store_true")
    c.set_defaults(func=cmd_clean)

    s = sub.add_parser("synthesize", help="full pipeline -> premium vertical mp4")
    s.add_argument("video", help="raw A-roll recording")
    s.add_argument("--reference", help="reference video to match the style of")
    s.add_argument("--transcript", help="word-timed transcript JSON")
    s.add_argument("--brand-db", help="brand board sqlite db")
    s.add_argument("--board", help="brand board id")
    s.add_argument("--out", required=True, help="output mp4")
    s.add_argument("--plan-out", help="also write the generation plan JSON")
    s.add_argument("--graph-out", help="also write the ffmpeg filtergraph")
    s.add_argument("--aggressive-fillers", action="store_true")
    s.set_defaults(func=cmd_synthesize)

    r = sub.add_parser("render", help="render a generation plan JSON")
    r.add_argument("plan")
    r.add_argument("--out", required=True)
    r.set_defaults(func=cmd_render)

    b = sub.add_parser("brand", help="manage brand boards")
    b.add_argument("--brand-db", default="cadence_brand.db")
    bsub = b.add_subparsers(dest="brand_cmd", required=True)
    bsub.add_parser("list")
    bc = bsub.add_parser("create")
    bc.add_argument("name")
    ba = bsub.add_parser("add-asset")
    ba.add_argument("board")
    ba.add_argument("path")
    ba.add_argument("--kind", default="watermark", choices=[k.value for k in AssetKind])
    ba.add_argument("--name", default="asset")
    ba.add_argument("--anchor", default="bottom_right", choices=[a.value for a in Anchor])
    ba.add_argument("--opacity", type=float, default=1.0)
    ba.add_argument("--scale", type=float, default=0.18)
    bcs = bsub.add_parser("caption-style")
    bcs.add_argument("board")
    bcs.add_argument("--primary")
    bcs.add_argument("--outline")
    bcs.add_argument("--font")
    b.set_defaults(func=cmd_brand)

    sv = sub.add_parser("serve", help="run the local HTTP sidecar")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--workspace", default="cadence_workspace")
    sv.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = EngineConfig()
    ff = FFmpeg(cfg.ffmpeg_bin, cfg.ffprobe_bin)
    try:
        return args.func(args, ff)
    except CadenceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
