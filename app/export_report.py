"""Generate the dashboard PNG report without starting the web server.

Usage (from the project root):

    python -m app.export_report
"""

from __future__ import annotations

from .analytics import build_dashboard_context, build_report_image


def main() -> None:
    print("Building dashboard charts...")
    context = build_dashboard_context()
    print("Composing the PNG report...")
    report_path = build_report_image(context)
    print(f"Report written to: {report_path}")
    print(f"Charts written to: exports/charts")


if __name__ == "__main__":
    main()
