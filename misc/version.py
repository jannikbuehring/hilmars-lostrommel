"""Single source of truth for the application name and version.

Imported by the startup banner (misc/startup_info.py) and by the HTML bracket
export (viewer/bracket_html_exporter.py) so the two can never drift apart.
Bump __version__ here and nowhere else.
"""

APP_NAME = "Hilmars Lostrommel"
__version__ = "1.0.1"
