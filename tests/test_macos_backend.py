"""Tests for the macOS platform backend (pyobjc-based)."""

import sys

import pytest


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
class TestMacOSBackend:
    def test_import(self):
        from voice_input_method.platform.macos import MacOSBackend
        assert MacOSBackend is not None

    def test_instantiation(self):
        from voice_input_method.platform.macos import MacOSBackend
        backend = MacOSBackend()
        assert backend._pasteboard is not None

    def test_check_permissions_returns_list(self):
        from voice_input_method.platform.macos import MacOSBackend
        backend = MacOSBackend()
        result = backend.check_permissions()
        assert isinstance(result, list)

    def test_implements_protocol(self):
        from voice_input_method.platform.macos import MacOSBackend
        from voice_input_method.protocols import TextPaster
        assert isinstance(MacOSBackend(), TextPaster)
