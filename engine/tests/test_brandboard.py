"""Unit tests for Module B (brand board persistence)."""

from __future__ import annotations

import pytest

from cadence.brandboard.store import BrandBoardStore
from cadence.errors import BrandBoardError
from cadence.models import Anchor, AssetKind, BrandPalette, RGBColor


@pytest.fixture
def store() -> BrandBoardStore:
    s = BrandBoardStore(":memory:")
    yield s
    s.close()


def test_create_and_get_board_roundtrip(store):
    board = store.create_board("Acme")
    fetched = store.get_board(board.id)
    assert fetched.id == board.id
    assert fetched.name == "Acme"
    assert fetched.palettes == []
    assert fetched.assets == []


def test_get_missing_board_raises(store):
    with pytest.raises(BrandBoardError):
        store.get_board("does-not-exist")


def test_add_palette_persists(store):
    board = store.create_board("Acme")
    palette = BrandPalette(name="Primary", colors=[RGBColor(255, 0, 0), RGBColor(0, 0, 255)])
    store.add_palette(board.id, palette)
    fetched = store.get_board(board.id)
    assert len(fetched.palettes) == 1
    assert [c.hex for c in fetched.palettes[0].colors] == ["#FF0000", "#0000FF"]


def test_add_asset_persists_and_roundtrips(store, logo_png):
    board = store.create_board("Acme")
    asset = store.add_asset(
        board.id, kind=AssetKind.WATERMARK, name="logo", path=logo_png,
        opacity=0.7, anchor=Anchor.BOTTOM_RIGHT, scale=0.2,
    )
    fetched = store.get_board(board.id)
    assert len(fetched.assets) == 1
    got = fetched.assets[0]
    assert got.id == asset.id
    assert got.kind == AssetKind.WATERMARK
    assert got.opacity == pytest.approx(0.7)
    assert got.anchor == Anchor.BOTTOM_RIGHT
    assert fetched.asset_of(AssetKind.WATERMARK) is not None


def test_add_asset_missing_file_raises(store):
    board = store.create_board("Acme")
    with pytest.raises(BrandBoardError):
        store.add_asset(board.id, kind=AssetKind.LOGO, name="x", path="nope.png")


def test_set_caption_style_and_delete(store):
    board = store.create_board("Acme")
    updated = store.set_caption_style(
        board.id, primary=RGBColor(255, 255, 255), outline=RGBColor(0, 0, 0), font_path="Montserrat.ttf"
    )
    assert updated.caption_primary == RGBColor(255, 255, 255)
    assert updated.caption_font_path == "Montserrat.ttf"
    store.delete_board(board.id)
    with pytest.raises(BrandBoardError):
        store.get_board(board.id)


def test_list_boards(store):
    store.create_board("B")
    store.create_board("A")
    names = [b.name for b in store.list_boards()]
    assert names == ["A", "B"]  # ordered by name
