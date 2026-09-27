"""Compatibility wrapper for the canonical CLI entrypoint."""

from .cli_app import build_parser, main, render_result

__all__ = ["build_parser", "main", "render_result"]
