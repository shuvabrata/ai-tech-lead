"""Pytest configuration for collaboration layer validation tests.

Collects per-layer results during the session and writes timestamped
HTML and JSON reports to tests/collab_validation/results/ on session finish.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest


# Accumulated per-layer results, populated by the track_result fixture.
_layer_results: list = []

_RESULTS_DIR = Path(__file__).parent / "results"
_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def track_result():
    """Fixture that lets a test register its result dict for the HTML report."""
    def _track(result: dict) -> None:
        _layer_results.append(result)
    return _track


def pytest_sessionfinish(session, exitstatus):
    """Generate HTML and JSON reports after all tests in this folder complete."""
    if not _layer_results:
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    total = len(_layer_results)
    passed = sum(1 for r in _layer_results if r["status"] == "PASS")
    failed = total - passed

    # -------------------------------------------------------------------------
    # JSON report
    # -------------------------------------------------------------------------
    report_data = {
        "generated_at": timestamp,
        "summary": {"total": total, "passed": passed, "failed": failed},
        "layers": _layer_results,
    }
    json_path = _RESULTS_DIR / f"test_results_{timestamp}.json"
    json_path.write_text(json.dumps(report_data, indent=2))
    (_RESULTS_DIR / "latest.json").write_text(json.dumps(report_data, indent=2))

    # -------------------------------------------------------------------------
    # HTML report
    # -------------------------------------------------------------------------
    rows = []
    for r in _layer_results:
        status = r["status"]
        color = "#2e7d32" if status == "PASS" else "#c62828"
        icon = "✅" if status == "PASS" else "❌"
        rows.append(
            f"<tr>"
            f"<td>{r['layer']}</td>"
            f"<td style='color:{color};font-weight:bold'>{icon} {status}</td>"
            f"<td>{r['row_count']}</td>"
            f"<td>{r['elapsed_ms']} ms</td>"
            f"<td>{r['message']}</td>"
            f"</tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Collaboration Layer Validation — {timestamp}</title>
  <style>
    body {{ font-family: Inter, sans-serif; margin: 40px; color: #333; }}
    h1 {{ font-size: 22px; margin-bottom: 4px; }}
    .meta {{ font-size: 13px; color: #666; margin-bottom: 24px; }}
    .summary {{ display: flex; gap: 24px; margin-bottom: 24px; }}
    .badge {{ padding: 8px 18px; border-radius: 4px; font-size: 14px; font-weight: 600; }}
    .pass {{ background: #e8f5e9; color: #2e7d32; }}
    .fail {{ background: #ffebee; color: #c62828; }}
    .total {{ background: #e3f2fd; color: #1565c0; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th {{ background: #f5f5f5; text-align: left; padding: 8px 12px; border-bottom: 2px solid #ddd; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
    tr:hover {{ background: #fafafa; }}
  </style>
</head>
<body>
  <h1>Collaboration Layer Validation</h1>
  <div class="meta">Generated: {timestamp}</div>
  <div class="summary">
    <span class="badge total">Total: {total}</span>
    <span class="badge pass">Passed: {passed}</span>
    <span class="badge fail">Failed: {failed}</span>
  </div>
  <table>
    <thead>
      <tr>
        <th>Layer</th><th>Status</th><th>Pairs Found</th><th>Duration</th><th>Message</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>"""

    html_path = _RESULTS_DIR / f"test_results_{timestamp}.html"
    html_path.write_text(html)
    (_RESULTS_DIR / "latest.html").write_text(html)

    print(f"\n✅ Collab validation report: {html_path}")
    print(f"   JSON: {json_path}")
