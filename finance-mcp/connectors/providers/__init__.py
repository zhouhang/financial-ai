"""Connector providers for each source kind."""

from connectors.providers.api import ApiConnector
from connectors.providers.browser import BrowserConnector
from connectors.providers.database import DatabaseConnector
from connectors.providers.desktop_cli import DesktopCliConnector
from connectors.providers.file_source import FileConnector
from connectors.providers.platform_oauth import PlatformOAuthConnector

__all__ = [
    "ApiConnector",
    "BrowserConnector",
    "DatabaseConnector",
    "DesktopCliConnector",
    "FileConnector",
    "PlatformOAuthConnector",
]

