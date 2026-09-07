"""Optional browser collector; importing Visparse never imports Playwright."""

from .browser import CaptureOptions, capture

__all__ = ["CaptureOptions", "capture"]
