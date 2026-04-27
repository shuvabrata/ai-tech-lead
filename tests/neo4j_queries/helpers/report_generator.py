"""
Report generation for query test results.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List

from .models import QueryResult, TestRunSummary


class ReportGenerator:
    """Generate various report formats from test results."""

    def _get_status_icon(self, status: str) -> str:
        """Get emoji icon for status."""
        icons = {
            "PASS": "✅",
            "WARNING": "⚠️ ",
            "CONCERN": "🔶",
            "FAIL": "❌"
        }
        return icons.get(status, "❓")
    
    def __init__(self, results_dir: Path = None):
        """Initialize report generator."""
        self.results_dir = results_dir or Path(__file__).parent.parent / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_json_report(self, results: List[QueryResult]) -> Path:
        """
        Generate JSON report and save to file.
        
        Args:
            results: List of QueryResult objects
            
        Returns:
            Path to generated JSON file
        """
        summary = self._calculate_summary(results)
        
        report = {
            "test_run": summary.to_dict(),
            "queries": [r.to_dict() for r in results]
        }
        
        # Save with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        json_file = self.results_dir / f"test_results_{timestamp}.json"
        
        with open(json_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Also save as latest.json
        latest_file = self.results_dir / "latest.json"
        with open(latest_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        return json_file
    
    def generate_console_report(self, results: List[QueryResult]) -> str:
        """
        Generate console-friendly text report.
        
        Args:
            results: List of QueryResult objects
            
        Returns:
            Formatted text report
        """
        summary = self._calculate_summary(results)
        
        lines = []
        lines.append("\n" + "=" * 80)
        lines.append(" Neo4j Query Validation Report".center(80))
        lines.append("=" * 80)
        lines.append(f"Date: {summary.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Total Queries: {summary.total_queries}")
        
        status_line = (
            f"✅ Pass: {summary.passed}  |  "
            f"⚠️  Warning: {summary.warnings}  |  "
            f"🔶 Concern: {summary.concerns}  |  "
            f"❌ Fail: {summary.failed}"
        )
        lines.append(status_line)
        lines.append("=" * 80)
        
        # Group by section
        sections = {}
        for result in results:
            if result.section not in sections:
                sections[result.section] = []
            sections[result.section].append(result)
        
        # Print each section
        for section_name, section_results in sections.items():
            lines.append(f"\n{section_name}")
            lines.append("─" * 80)
            
            for r in section_results:
                status_icon = self._get_status_icon(r.status)
                time_str = f"{r.execution_time_ms:6.0f}ms"
                rows_str = f"{r.row_count:4} rows"
                
                line = f"{status_icon} {r.query_name:45} {time_str:>10}  {rows_str:>10}"
                lines.append(line)
                
                # Add details for non-PASS statuses
                if r.status != "PASS" and r.details:
                    lines.append(f"    → {r.details}")
                
                # Add query preview
                query_preview = r.query_text.strip().replace('\n', ' ')[:80]
                lines.append(f"    Query: {query_preview}...")
                
                # Add result preview
                if r.result_rows:
                    lines.append(f"    Results: First {len(r.result_rows)} of {r.row_count} rows")
                    # Show first row as sample
                    if r.result_rows:
                        first_row = r.result_rows[0]
                        for key, val in list(first_row.items())[:3]:  # Show first 3 columns
                            display_val = str(val)[:40] if val is not None else "NULL"
                            lines.append(f"      {key}: {display_val}")
                elif r.row_count == 0:
                    lines.append(f"    Results: No data returned")
        
        # Summary statistics
        lines.append("\n" + "=" * 80)
        lines.append("Summary Statistics")
        lines.append("─" * 80)
        lines.append(f"Average execution time: {summary.avg_execution_time_ms:.1f}ms")
        
        if summary.slowest_queries:
            lines.append(f"\nSlowest queries:")
            for sq in summary.slowest_queries[:5]:
                lines.append(f"  {sq['name']:50} {sq['time_ms']:>8.0f}ms")
        
        # Queries with concerns
        concerns = [r for r in results if r.status in ("WARNING", "CONCERN")]
        if concerns:
            lines.append(f"\nQueries needing attention ({len(concerns)}):")
            for c in concerns[:10]:  # Top 10
                lines.append(f"  [{c.status}] {c.query_name}: {c.details}")
        
        lines.append("=" * 80 + "\n")
        
        return "\n".join(lines)
    
    def generate_html_report(self, results: List[QueryResult]) -> Path:
        """
        Generate HTML report.
        
        Args:
            results: List of QueryResult objects
            
        Returns:
            Path to generated HTML file
        """
        summary = self._calculate_summary(results)
        
        html = self._build_html(summary, results)
        
        # Save with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        html_file = self.results_dir / f"test_results_{timestamp}.html"
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Also save as latest.html
        latest_file = self.results_dir / "latest.html"
        with open(latest_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return html_file
    
    def _calculate_summary(self, results: List[QueryResult]) -> TestRunSummary:
        """Calculate summary statistics from results."""
        summary = TestRunSummary(
            timestamp=datetime.now(),
            total_queries=len(results)
        )
        
        for r in results:
            if r.status == "PASS":
                summary.passed += 1
            elif r.status == "WARNING":
                summary.warnings += 1
            elif r.status == "CONCERN":
                summary.concerns += 1
            elif r.status == "FAIL":
                summary.failed += 1
        
        # Calculate average execution time
        if results:
            summary.avg_execution_time_ms = sum(r.execution_time_ms for r in results) / len(results)
        # Find slowest queries
        sorted_by_time = sorted(results, key=lambda r: r.execution_time_ms, reverse=True)
        summary.slowest_queries = [
            {"name": r.query_name, "time_ms": r.execution_time_ms}
            for r in sorted_by_time[:10]
        ]
        return summary
    
    def _build_html(self, summary: TestRunSummary, results: List[QueryResult]) -> str:
        """Build HTML report."""
        # Group by section
        sections = {}
        for result in results:
            if result.section not in sections:
                sections[result.section] = []
            sections[result.section].append(result)
        
        # Build HTML
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset=\"UTF-8\">
    <title>Neo4j Query Validation Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat {{ background: white; padding: 15px; border-radius: 5px; flex: 1; text-align: center; }}
        .stat-value {{ font-size: 2em; font-weight: bold; }}
        .stat-label {{ color: #666; margin-top: 5px; }}
        .pass {{ color: #27ae60; }}
        .warning {{ color: #f39c12; }}
        .concern {{ color: #e67e22; }}
        .fail {{ color: #e74c3c; }}
        .section {{ background: white; margin: 20px 0; padding: 20px; border-radius: 5px; }}
        .section-title {{ font-size: 1.3em; margin-bottom: 15px; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #34495e; color: white; }}
        tr:hover {{ background: #f8f9fa; }}
        .details {{ font-size: 0.9em; color: #666; margin-left: 20px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Neo4j Query Validation Report</h1>
        <p>Generated: {summary.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="summary">
        <div class="stat">
            <div class="stat-value">{summary.total_queries}</div>
            <div class="stat-label">Total Queries</div>
        </div>
        <div class="stat pass">
            <div class="stat-value">{summary.passed}</div>
            <div class="stat-label">✅ Passed</div>
        </div>
        <div class="stat warning">
            <div class="stat-value">{summary.warnings}</div>
            <div class="stat-label">⚠️ Warnings</div>
        </div>
        <div class="stat concern">
            <div class="stat-value">{summary.concerns}</div>
            <div class="stat-label">🔶 Concerns</div>
        </div>
        <div class="stat fail">
            <div class="stat-value">{summary.failed}</div>
            <div class="stat-label">❌ Failed</div>
        </div>
    </div>
"""
        
        # Add each section
        for section_name, section_results in sections.items():
            html += f"""
    <div class="section">
        <div class="section-title">{section_name}</div>
        <table>
            <tr>
                <th>Status</th>
                <th>Query</th>
                <th>Time (ms)</th>
                <th>Rows</th>
                <th>Details</th>
            </tr>
"""
            for r in section_results:
                icon = self._get_status_icon(r.status)
                status_class = r.status.lower()
                
                # Format query text for display
                query_preview = r.query_text.strip()[:100] + "..." if len(r.query_text.strip()) > 100 else r.query_text.strip()
                query_preview = query_preview.replace('\n', ' ')
                
                # Format results preview
                results_preview = ""
                if r.result_rows:
                    results_preview = f"{len(r.result_rows)} rows returned"
                elif r.row_count == 0:
                    results_preview = "No data"
                
                html += f"""
            <tr class="{status_class}">
                <td>{icon}</td>
                <td>
                    <strong>{r.query_name}</strong><br/>
                    <small style="color: #666;">{query_preview}</small>
                </td>
                <td>{r.execution_time_ms:.0f}</td>
                <td>{r.row_count}</td>
                <td>
                    {r.details}<br/>
                    <small style="color: #666;">{results_preview}</small>
                </td>
            </tr>
"""
                
                # Add expandable query details and results
                if r.result_rows or r.query_text:
                    html += f"""
            <tr>
                <td colspan="5" style="background: #f8f9fa; padding: 15px;">
                    <details>
                        <summary style="cursor: pointer; font-weight: bold;">View Query & Results</summary>
                        <div style="margin-top: 10px;">
                            <h4>Query:</h4>
                            <pre style="background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 5px; overflow-x: auto;">{r.query_text}</pre>
"""
                    
                    if r.result_rows:
                        html += """
                            <h4>Results (limited to 10 rows):</h4>
                            <table style="width: 100%; font-size: 0.9em;">
                                <tr style="background: #34495e;">
"""
                        # Column headers
                        if r.result_rows:
                            for col in r.result_rows[0].keys():
                                html += f"<th>{col}</th>"
                        html += "</tr>"
                        
                        # Data rows
                        for row in r.result_rows:
                            html += "<tr>"
                            for val in row.values():
                                # Always render as string for graph/path results
                                display_val = str(val) if val is not None else "<em>NULL</em>"
                                html += f"<td style='font-family:monospace;font-size:0.9em'>{display_val}</td>"
                            html += "</tr>"
                        html += "</table>"
                    else:
                        html += "<p><em>No results returned</em></p>"
                    
                    html += """
                        </div>
                    </details>
                </td>
            </tr>
"""
            html += """
        </table>
    </div>
"""
        
        html += """
</body>
</html>
"""
        return html
