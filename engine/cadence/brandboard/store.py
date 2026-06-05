"""§3 Module B — a localized, secure SQLite store for brand equity assets.

Logos/watermarks, custom fonts, colour palettes, and pre-rendered overlays persist
across sessions and are applied at synthesis time. SQLite (stdlib) keeps it
dependency-free and embeddable inside the Flutter desktop/mobile sidecar.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid

from cadence.errors import BrandBoardError
from cadence.models import (
    Anchor,
    AssetKind,
    BrandAsset,
    BrandBoard,
    BrandPalette,
    RGBColor,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS brand_boards (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    caption_font_path TEXT,
    caption_primary   TEXT,
    caption_outline   TEXT
);
CREATE TABLE IF NOT EXISTS brand_palettes (
    id        TEXT PRIMARY KEY,
    board_id  TEXT NOT NULL REFERENCES brand_boards(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    colors    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS brand_assets (
    id        TEXT PRIMARY KEY,
    board_id  TEXT NOT NULL REFERENCES brand_boards(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL,
    name      TEXT NOT NULL,
    path      TEXT NOT NULL,
    opacity   REAL NOT NULL DEFAULT 1.0,
    anchor    TEXT NOT NULL DEFAULT 'bottom_right',
    scale     REAL NOT NULL DEFAULT 1.0,
    meta      TEXT NOT NULL DEFAULT '{}'
);
"""


def _new_id() -> str:
    return uuid.uuid4().hex


class BrandBoardStore:
    """CRUD persistence for :class:`BrandBoard`. Pass ``:memory:`` for ephemeral use."""

    def __init__(self, db_path: str = "cadence_brand.db") -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "BrandBoardStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- boards ------------------------------------------------------------- #
    def create_board(self, name: str) -> BrandBoard:
        board = BrandBoard(id=_new_id(), name=name)
        self._conn.execute(
            "INSERT INTO brand_boards (id, name, caption_font_path, caption_primary, caption_outline)"
            " VALUES (?,?,?,?,?)",
            (board.id, board.name, None, None, None),
        )
        self._conn.commit()
        return board

    def list_boards(self) -> list[BrandBoard]:
        rows = self._conn.execute("SELECT id FROM brand_boards ORDER BY name").fetchall()
        return [self.get_board(r["id"]) for r in rows]

    def get_board(self, board_id: str) -> BrandBoard:
        row = self._conn.execute("SELECT * FROM brand_boards WHERE id=?", (board_id,)).fetchone()
        if row is None:
            raise BrandBoardError(f"brand board not found: {board_id}")
        palettes = [
            BrandPalette(
                name=p["name"],
                colors=[RGBColor.from_hex(c) for c in json.loads(p["colors"])],
            )
            for p in self._conn.execute(
                "SELECT * FROM brand_palettes WHERE board_id=?", (board_id,)
            ).fetchall()
        ]
        assets = [
            BrandAsset(
                id=a["id"],
                kind=AssetKind(a["kind"]),
                name=a["name"],
                path=a["path"],
                opacity=a["opacity"],
                anchor=Anchor(a["anchor"]),
                scale=a["scale"],
                meta=json.loads(a["meta"]),
            )
            for a in self._conn.execute(
                "SELECT * FROM brand_assets WHERE board_id=?", (board_id,)
            ).fetchall()
        ]
        return BrandBoard(
            id=row["id"],
            name=row["name"],
            palettes=palettes,
            assets=assets,
            caption_font_path=row["caption_font_path"],
            caption_primary=RGBColor.from_hex(row["caption_primary"]) if row["caption_primary"] else None,
            caption_outline=RGBColor.from_hex(row["caption_outline"]) if row["caption_outline"] else None,
        )

    def delete_board(self, board_id: str) -> None:
        self._conn.execute("DELETE FROM brand_boards WHERE id=?", (board_id,))
        self._conn.commit()

    def set_caption_style(
        self,
        board_id: str,
        *,
        font_path: str | None = None,
        primary: RGBColor | None = None,
        outline: RGBColor | None = None,
    ) -> BrandBoard:
        self._require(board_id)
        self._conn.execute(
            "UPDATE brand_boards SET caption_font_path=?, caption_primary=?, caption_outline=? WHERE id=?",
            (
                font_path,
                primary.hex if primary else None,
                outline.hex if outline else None,
                board_id,
            ),
        )
        self._conn.commit()
        return self.get_board(board_id)

    # -- palettes ----------------------------------------------------------- #
    def add_palette(self, board_id: str, palette: BrandPalette) -> BrandBoard:
        self._require(board_id)
        self._conn.execute(
            "INSERT INTO brand_palettes (id, board_id, name, colors) VALUES (?,?,?,?)",
            (_new_id(), board_id, palette.name, json.dumps([c.hex for c in palette.colors])),
        )
        self._conn.commit()
        return self.get_board(board_id)

    # -- assets ------------------------------------------------------------- #
    def add_asset(
        self,
        board_id: str,
        *,
        kind: AssetKind,
        name: str,
        path: str,
        opacity: float = 1.0,
        anchor: Anchor = Anchor.BOTTOM_RIGHT,
        scale: float = 0.18,
        meta: dict | None = None,
        require_file: bool = True,
    ) -> BrandAsset:
        self._require(board_id)
        if require_file and not os.path.isfile(path):
            raise BrandBoardError(f"asset file not found: {path}")
        asset = BrandAsset(
            id=_new_id(), kind=kind, name=name, path=path,
            opacity=opacity, anchor=anchor, scale=scale, meta=meta or {},
        )
        self._conn.execute(
            "INSERT INTO brand_assets (id, board_id, kind, name, path, opacity, anchor, scale, meta)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                asset.id, board_id, asset.kind.value, asset.name, asset.path,
                asset.opacity, asset.anchor.value, asset.scale, json.dumps(asset.meta),
            ),
        )
        self._conn.commit()
        return asset

    def remove_asset(self, asset_id: str) -> None:
        self._conn.execute("DELETE FROM brand_assets WHERE id=?", (asset_id,))
        self._conn.commit()

    def _require(self, board_id: str) -> None:
        if self._conn.execute("SELECT 1 FROM brand_boards WHERE id=?", (board_id,)).fetchone() is None:
            raise BrandBoardError(f"brand board not found: {board_id}")
