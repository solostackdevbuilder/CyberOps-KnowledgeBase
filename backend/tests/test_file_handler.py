"""
Tests for the screenshot file handler.

Focus areas:
- session_id validation: defense-in-depth against filename path traversal,
  since save_screenshot builds the on-disk filename directly from session_id.
- Content-type → extension mapping.
- URL parsing resilience (malformed URLs must not crash the save path).
"""
import asyncio
import io
import unittest
from unittest.mock import patch

from PIL import Image

from app.utils.file_handler import (
    _get_extension_from_content_type,
    _validate_session_id,
    save_screenshot,
)


def _run(coro):
    return asyncio.run(coro)


class ValidateSessionIdTests(unittest.TestCase):
    """Reject anything that could escape screenshots_dir when formatted
    into a filename. Pathlib interprets `/` and `\\` as separators, so a
    session_id containing them would write outside the target directory."""

    def test_accepts_uuid_shaped_id(self) -> None:
        _validate_session_id("602c64cc-94ec-49e7-8609-bee1201ea082")

    def test_accepts_short_alphanumeric(self) -> None:
        _validate_session_id("abc123")

    def test_rejects_forward_slash(self) -> None:
        with self.assertRaises(ValueError):
            _validate_session_id("../../etc/passwd")

    def test_rejects_backslash(self) -> None:
        with self.assertRaises(ValueError):
            _validate_session_id("..\\..\\etc")

    def test_rejects_dot_dot_alone(self) -> None:
        with self.assertRaises(ValueError):
            _validate_session_id("..")

    def test_rejects_null_byte(self) -> None:
        with self.assertRaises(ValueError):
            _validate_session_id("abc\x00def")

    def test_rejects_empty_string(self) -> None:
        with self.assertRaises(ValueError):
            _validate_session_id("")

    def test_rejects_overlong_id(self) -> None:
        with self.assertRaises(ValueError):
            _validate_session_id("a" * 65)

    def test_rejects_non_string(self) -> None:
        with self.assertRaises(ValueError):
            _validate_session_id(12345)  # type: ignore[arg-type]

    def test_rejects_shell_metachars(self) -> None:
        for bad in ("a;b", "a|b", "a`b`", "a$b", "a b"):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    _validate_session_id(bad)


class ContentTypeExtensionTests(unittest.TestCase):
    def test_known_types_map_correctly(self) -> None:
        self.assertEqual(_get_extension_from_content_type("image/png"), "png")
        self.assertEqual(_get_extension_from_content_type("image/jpeg"), "jpg")
        self.assertEqual(_get_extension_from_content_type("image/jpg"), "jpg")
        self.assertEqual(_get_extension_from_content_type("image/gif"), "gif")
        self.assertEqual(_get_extension_from_content_type("image/webp"), "webp")
        self.assertEqual(_get_extension_from_content_type("image/bmp"), "bmp")

    def test_case_insensitive(self) -> None:
        self.assertEqual(_get_extension_from_content_type("Image/PNG"), "png")

    def test_none_returns_none(self) -> None:
        self.assertIsNone(_get_extension_from_content_type(None))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(_get_extension_from_content_type(""))

    def test_unknown_type_returns_none(self) -> None:
        # Falls through to PIL format inference at the call site.
        self.assertIsNone(_get_extension_from_content_type("application/pdf"))
        self.assertIsNone(_get_extension_from_content_type("image/heic"))


# ---------------------------------------------------------------------------
# Integration-lite: save_screenshot with a fake UploadFile. Verifies that
# session_id validation triggers before any file IO happens.
# ---------------------------------------------------------------------------


class _FakeUpload:
    """Minimal stand-in for fastapi.UploadFile used only for these tests.

    Carries a PNG byte buffer that PIL can open, and provides the
    read/seek shape that save_screenshot uses.
    """

    def __init__(self, data: bytes, content_type: str = "image/png"):
        self._buf = io.BytesIO(data)
        self.content_type = content_type

    @property
    def file(self) -> io.BytesIO:
        return self._buf

    async def read(self, size: int = -1) -> bytes:
        return self._buf.read(size if size >= 0 else None)

    async def seek(self, pos: int) -> None:
        self._buf.seek(pos)


def _make_png_bytes() -> bytes:
    img = Image.new("RGB", (4, 4), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class SaveScreenshotGuardTests(unittest.TestCase):
    def test_bad_session_id_raises_before_disk_write(self) -> None:
        """Malformed session_id must be rejected before any IO happens.

        If this test regresses, the filename-injection surface is open
        again - a caller could write to ../../arbitrary paths.
        """
        data = _make_png_bytes()
        fake = _FakeUpload(data)

        with self.assertRaises(ValueError):
            _run(save_screenshot(fake, "../../etc/passwd"))

    def test_rejects_session_id_with_separator_without_touching_disk(self) -> None:
        data = _make_png_bytes()
        fake = _FakeUpload(data)

        # If validation fails, _ensure_directory / aiofiles.open should
        # never be reached. Patch them to flag any unexpected IO.
        with patch("app.utils.file_handler._ensure_directory") as ensure, \
             patch("app.utils.file_handler.aiofiles.open") as opener:
            with self.assertRaises(ValueError):
                _run(save_screenshot(fake, "a/b"))
            ensure.assert_not_called()
            opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
