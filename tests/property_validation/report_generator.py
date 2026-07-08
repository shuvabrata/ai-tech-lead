"""
Generate reports for property validation results.
"""

import json
from pathlib import Path
from typing import List
from tests.property_validation.models import ValidationReport, PropertyValidationResult, PopulationCategory, StubNodeResult


# ANSI color codes for console output
class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def generate_console_report(report: ValidationReport) -> None:
    """
    Generate and print console report with colored output.
    
    Args:
        report: ValidationReport to display
    """
    print(f"\n{Colors.BOLD}{'='*100}")
    print(f"PROPERTY VALIDATION REPORT")
    print(f"Generated: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*100}{Colors.RESET}\n")
    
    # Summary
    summary = report._generate_summary()
    print(f"{Colors.BOLD}SUMMARY{Colors.RESET}")
    print(f"  Entity Types: {summary['total_entity_types']}")
    print(f"  Relationship Types: {summary['total_relationship_types']}")
    print(f"  Relationship Existence Checks: {summary.get('total_relationship_existence_checks', 0)}")
    print(f"  Total Properties: {summary['total_properties_validated']}")
    print(f"  {Colors.GREEN}✓ Full Population (100%): {summary['full_population']}{Colors.RESET}")
    print(f"  {Colors.YELLOW}⚠ Partial Population (1-99%): {summary['partial_population']}{Colors.RESET}")
    print(f"  {Colors.RED}✗ Empty (0%): {summary['empty_population']}{Colors.RESET}")
    if summary['failures'] > 0:
        print(f"  {Colors.RED}{Colors.BOLD}❌ FAILURES (Required properties at 0%): {summary['failures']}{Colors.RESET}")
    else:
        print(f"  {Colors.GREEN}✓ No failures{Colors.RESET}")
    
    # Relationship coverage summary
    if 'relationship_coverage' in summary:
        cov = summary['relationship_coverage']
        print(f"\n{Colors.BOLD}RELATIONSHIP COVERAGE{Colors.RESET}")
        print(f"  Expected: {cov['expected']}")
        print(f"  Discovered: {cov['discovered']}")
        print(f"  Coverage: {Colors.GREEN if cov['coverage_percentage'] >= 95 else Colors.YELLOW}{cov['coverage_percentage']:.1f}%{Colors.RESET}")
        if cov['missing'] > 0:
            print(f"  {Colors.RED}Missing: {cov['missing']}{Colors.RESET}")
        if cov['unexpected'] > 0:
            print(f"  {Colors.YELLOW}Unexpected: {cov['unexpected']}{Colors.RESET}")
    print()
    
    # Relationship Coverage Details
    if report.relationship_coverage:
        _print_relationship_coverage(report.relationship_coverage)
    
    # Relationship Existence
    if report.relationship_existence:
        _print_relationship_existence(report.relationship_existence)
    
    # Entity results
    if report.entity_results:
        print(f"{Colors.BOLD}{'='*100}")
        print(f"ENTITY PROPERTIES")
        print(f"{'='*100}{Colors.RESET}\n")
        
        for entity_type in sorted(report.entity_results.keys()):
            results = report.entity_results[entity_type]
            _print_entity_table(entity_type, results)
    
    # Relationship results
    if report.relationship_results:
        print(f"{Colors.BOLD}{'='*100}")
        print(f"RELATIONSHIP PROPERTIES")
        print(f"{'='*100}{Colors.RESET}\n")
        
        for rel_type in sorted(report.relationship_results.keys()):
            results = report.relationship_results[rel_type]
            _print_relationship_table(rel_type, results)

    # Stub nodes
    if report.stub_node_results:
        _print_stub_nodes(report.stub_node_results)


def _print_stub_nodes(stub_node_results: dict) -> None:
    """Print stub node detection results to the console."""
    labels_with_stubs = {label: r for label, r in stub_node_results.items() if r.stub_count > 0}
    total_stubs = sum(r.stub_count for r in stub_node_results.values())

    print(f"{Colors.BOLD}{'='*100}")
    print(f"STUB NODES")
    print(f"{'='*100}{Colors.RESET}\n")
    print(f"A stub node has only its 'id' property set — all other properties are absent.")
    print(f"id format: <connector>::<entity_type>::<unique_id>\n")

    if total_stubs == 0:
        print(f"{Colors.GREEN}✓ No stub nodes found across {len(stub_node_results)} labels{Colors.RESET}\n")
        return

    print(f"{Colors.YELLOW}⚠️  {total_stubs} stub nodes found in {len(labels_with_stubs)} label(s){Colors.RESET}\n")

    for label, result in sorted(labels_with_stubs.items()):
        pct_str = f"{result.stub_percentage:.1f}%"
        print(f"{Colors.BOLD}{Colors.BLUE}{label}{Colors.RESET}  "
              f"— stubs: {Colors.YELLOW}{result.stub_count}{Colors.RESET}/{result.total_count} ({pct_str})")
        print(f"  {'Connector':<25} {'Entity Type':<30} {'Count':<10}")
        print(f"  {'-'*65}")
        for b in result.breakdown:
            print(f"  {b.connector:<25} {b.entity_type:<30} {b.count:<10}")
        print()


def _print_entity_table(entity_type: str, results: List[PropertyValidationResult]) -> None:
    """Print a table for entity property validation results."""
    print(f"{Colors.BOLD}{Colors.BLUE}{entity_type}{Colors.RESET}")
    print(f"{'-'*100}")
    
    # Header
    header = f"{'Property':<30} {'Required':<10} {'Total':<8} {'Populated':<10} {'Empty':<8} {'%':<8} {'Category':<10}"
    print(header)
    print(f"{'-'*100}")
    
    # Sort by required first, then by category (EMPTY, PARTIAL, FULL)
    sorted_results = sorted(results, key=lambda r: (not r.is_required, r.category.value))
    
    for result in sorted_results:
        req_str = "YES" if result.is_required else "no"
        
        # Color code the category
        if result.category == PopulationCategory.FULL:
            category_str = f"{Colors.GREEN}FULL{Colors.RESET}"
            pct_str = f"{Colors.GREEN}{result.population_percentage:6.2f}%{Colors.RESET}"
        elif result.category == PopulationCategory.PARTIAL:
            category_str = f"{Colors.YELLOW}PARTIAL{Colors.RESET}"
            pct_str = f"{Colors.YELLOW}{result.population_percentage:6.2f}%{Colors.RESET}"
        else:
            category_str = f"{Colors.RED}EMPTY{Colors.RESET}"
            pct_str = f"{Colors.RED}{result.population_percentage:6.2f}%{Colors.RESET}"
            if result.is_required:
                category_str = f"{Colors.RED}{Colors.BOLD}EMPTY ❌{Colors.RESET}"
        
        row = f"{result.property_name:<30} {req_str:<10} {result.total_count:<8} {result.populated_count:<10} {result.empty_count:<8} {pct_str:<15} {category_str}"
        print(row)
    
    print()

def _print_relationship_coverage(coverage) -> None:
    """Print relationship coverage section."""
    print(f"{Colors.BOLD}{'='*100}")
    print(f"RELATIONSHIP COVERAGE DETAILS")
    print(f"{'='*100}{Colors.RESET}\n")
    
    print(f"{Colors.BOLD}Expected: {coverage.expected_count} | Discovered: {coverage.discovered_count} | Coverage: {(coverage.discovered_count/coverage.expected_count*100):.1f}%{Colors.RESET}\n")
    
    if coverage.missing_relationships:
        print(f"{Colors.RED}{Colors.BOLD}MISSING RELATIONSHIPS ({len(coverage.missing_relationships)}){Colors.RESET}")
        print(f"{Colors.RED}These relationships are expected but not found in the database:{Colors.RESET}")
        for rel in coverage.missing_relationships:
            print(f"  ✗ {rel}")
        print()
    
    if coverage.unexpected_relationships:
        print(f"{Colors.YELLOW}{Colors.BOLD}UNEXPECTED RELATIONSHIPS ({len(coverage.unexpected_relationships)}){Colors.RESET}")
        print(f"{Colors.YELLOW}These relationships are in the database but not defined in db/models.py:{Colors.RESET}")
        for rel in coverage.unexpected_relationships:
            print(f"  ? {rel}")
        print()
    
    if coverage.bidirectional_mismatches:
        print(f"{Colors.RED}{Colors.BOLD}DIRECTIONAL MISMATCHES ({len(coverage.bidirectional_mismatches)}){Colors.RESET}")
        print(f"{Colors.RED}These directional relationships are missing their reverse:{Colors.RESET}")
        for rel in coverage.bidirectional_mismatches:
            print(f"  ⚠ {rel}")
        print()
    
    if not coverage.missing_relationships and not coverage.unexpected_relationships and not coverage.bidirectional_mismatches:
        print(f"{Colors.GREEN}✓ All expected relationships are present and consistent{Colors.RESET}\n")


def _print_relationship_existence(existence_dict) -> None:
    """Print relationship existence section."""
    print(f"{Colors.BOLD}{'='*100}")
    print(f"RELATIONSHIP EXISTENCE & CONSISTENCY")
    print(f"{'='*100}{Colors.RESET}\n")
    
    # Group by expected vs unexpected
    expected = {k: v for k, v in existence_dict.items() if v.is_expected}
    unexpected = {k: v for k, v in existence_dict.items() if not v.is_expected}
    
    # Expected relationships
    if expected:
        print(f"{Colors.BOLD}EXPECTED RELATIONSHIPS ({len(expected)}){Colors.RESET}")
        print(f"{'-'*100}")
        header = f"{'Relationship':<25} {'Count':<10} {'Props':<8} {'Directionality':<15} {'Reverse':<25} {'Rev Count':<10} {'Diff':<10}"
        print(header)
        print(f"{'-'*100}")
        
        for rel_type in sorted(expected.keys()):
            result = expected[rel_type]
            
            # Format directionality
            if result.is_same_name_bidirectional:
                bidir_str = f"{Colors.GREEN}Undirected{Colors.RESET}"
            elif result.is_bidirectional:
                bidir_str = f"{Colors.BLUE}Directional{Colors.RESET}"
            else:
                bidir_str = "No"
            
            # Format reverse info
            reverse_str = result.reverse_rel_type or "-"
            rev_count_str = str(result.reverse_count) if result.reverse_count is not None else "-"
            
            # Format discrepancy
            if result.count_discrepancy is not None:
                if result.count_discrepancy == 0:
                    diff_str = f"{Colors.GREEN}0{Colors.RESET}"
                elif result.count_discrepancy < 10:
                    diff_str = f"{Colors.YELLOW}{result.count_discrepancy}{Colors.RESET}"
                else:
                    diff_str = f"{Colors.RED}{result.count_discrepancy}{Colors.RESET}"
            else:
                diff_str = "-"
            
            # Format props
            props_str = f"{Colors.GREEN}Yes{Colors.RESET}" if result.has_properties else "No"
            
            row = f"{rel_type:<25} {result.total_count:<10} {props_str:<15} {bidir_str:<22} {reverse_str:<25} {rev_count_str:<10} {diff_str:<17}"
            print(row)
        print()
    
    # Unexpected relationships
    if unexpected:
        print(f"{Colors.YELLOW}{Colors.BOLD}UNEXPECTED RELATIONSHIPS ({len(unexpected)}){Colors.RESET}")
        print(f"{Colors.YELLOW}These are not defined in model relationship definitions:{Colors.RESET}")
        print(f"{'-'*100}")
        for rel_type in sorted(unexpected.keys()):
            result = unexpected[rel_type]
            props_str = "with properties" if result.has_properties else "no properties"
            print(f"  ? {rel_type:<30} Count: {result.total_count:<10} ({props_str})")
        print()

def _print_relationship_table(rel_type: str, results: List[PropertyValidationResult]) -> None:
    """Print a table for relationship property validation results."""
    print(f"{Colors.BOLD}{Colors.BLUE}{rel_type}{Colors.RESET}")
    print(f"{'-'*100}")
    
    # Header (no "Required" column for relationships)
    header = f"{'Property':<30} {'Total':<8} {'Populated':<10} {'Empty':<8} {'%':<8} {'Category':<10}"
    print(header)
    print(f"{'-'*100}")
    
    # Sort by category
    sorted_results = sorted(results, key=lambda r: r.category.value)
    
    for result in sorted_results:
        # Color code the category
        if result.category == PopulationCategory.FULL:
            category_str = f"{Colors.GREEN}FULL{Colors.RESET}"
            pct_str = f"{Colors.GREEN}{result.population_percentage:6.2f}%{Colors.RESET}"
        elif result.category == PopulationCategory.PARTIAL:
            category_str = f"{Colors.YELLOW}PARTIAL{Colors.RESET}"
            pct_str = f"{Colors.YELLOW}{result.population_percentage:6.2f}%{Colors.RESET}"
        else:
            category_str = f"{Colors.RED}EMPTY{Colors.RESET}"
            pct_str = f"{Colors.RED}{result.population_percentage:6.2f}%{Colors.RESET}"
        
        row = f"{result.property_name:<30} {result.total_count:<8} {result.populated_count:<10} {result.empty_count:<8} {pct_str:<15} {category_str}"
        print(row)
    
    print()


def generate_json_report(report: ValidationReport, output_path: Path) -> None:
    """
    Generate JSON report file.
    
    Args:
        report: ValidationReport to save
        output_path: Path to write JSON file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(report.to_dict(), f, indent=2)
    
    print(f"{Colors.GREEN}✓ JSON report saved to: {output_path}{Colors.RESET}")


def generate_html_report(report: ValidationReport, output_path: Path) -> None:
    """
    Generate HTML report file with interactive tables.
    
    Args:
        report: ValidationReport to save
        output_path: Path to write HTML file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    summary = report._generate_summary()
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Property Validation Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
            border-bottom: 2px solid #ddd;
            padding-bottom: 8px;
        }}
        .summary {{
            background-color: #f9f9f9;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}
        .summary-item {{
            padding: 10px;
            border-left: 4px solid #4CAF50;
        }}
        .summary-item strong {{
            display: block;
            font-size: 0.9em;
            color: #666;
        }}
        .summary-item .value {{
            font-size: 1.8em;
            font-weight: bold;
            color: #333;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 0.95em;
        }}
        th {{
            background-color: #4CAF50;
            color: white;
            padding: 12px;
            text-align: left;
            position: sticky;
            top: 0;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .entity-section {{
            margin: 30px 0;
        }}
        .entity-name {{
            font-size: 1.3em;
            font-weight: bold;
            color: #2196F3;
            margin: 15px 0 10px 0;
        }}
        .category-FULL {{
            background-color: #4CAF50;
            color: white;
            padding: 4px 8px;
            border-radius: 3px;
            font-weight: bold;
        }}
        .category-PARTIAL {{
            background-color: #FF9800;
            color: white;
            padding: 4px 8px;
            border-radius: 3px;
            font-weight: bold;
        }}
        .category-EMPTY {{
            background-color: #f44336;
            color: white;
            padding: 4px 8px;
            border-radius: 3px;
            font-weight: bold;
        }}
        .required-yes {{
            font-weight: bold;
            color: #d32f2f;
        }}
        .required-no {{
            color: #999;
        }}
        .failure-badge {{
            background-color: #f44336;
            color: white;
            padding: 2px 6px;
            border-radius: 3px;
            margin-left: 5px;
            font-size: 0.85em;
        }}
        .timestamp {{
            color: #999;
            font-size: 0.9em;
        }}
        .search-box {{
            margin: 20px 0;
            padding: 10px;
            width: 100%;
            font-size: 1em;
            border: 2px solid #ddd;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Property Validation Report</h1>
        <p class="timestamp">Generated: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="summary">
            <div class="summary-item">
                <strong>Entity Types</strong>
                <div class="value">{summary['total_entity_types']}</div>
            </div>
            <div class="summary-item">
                <strong>Relationship Types (with properties)</strong>
                <div class="value">{summary['total_relationship_types']}</div>
            </div>
            <div class="summary-item">
                <strong>Relationship Existence Checks</strong>
                <div class="value">{summary.get('total_relationship_existence_checks', 0)}</div>
            </div>
            <div class="summary-item">
                <strong>Total Properties</strong>
                <div class="value">{summary['total_properties_validated']}</div>
            </div>
            <div class="summary-item" style="border-left-color: #4CAF50;">
                <strong>Full Population</strong>
                <div class="value" style="color: #4CAF50;">{summary['full_population']}</div>
            </div>
            <div class="summary-item" style="border-left-color: #FF9800;">
                <strong>Partial Population</strong>
                <div class="value" style="color: #FF9800;">{summary['partial_population']}</div>
            </div>
            <div class="summary-item" style="border-left-color: #f44336;">
                <strong>Empty</strong>
                <div class="value" style="color: #f44336;">{summary['empty_population']}</div>
            </div>
            <div class="summary-item" style="border-left-color: {'#f44336' if summary['failures'] > 0 else '#4CAF50'};">
                <strong>Failures</strong>
                <div class="value" style="color: {'#f44336' if summary['failures'] > 0 else '#4CAF50'};">{summary['failures']}</div>
            </div>
        </div>
        
        <input type="text" class="search-box" id="searchBox" placeholder="Search entities, properties, or categories..." onkeyup="searchTable()">
        
        <h2>Entity Properties</h2>
"""
    
    # Add entity tables
    for entity_type in sorted(report.entity_results.keys()):
        results = report.entity_results[entity_type]
        html_content += _generate_entity_table_html(entity_type, results)
    
    # Add relationship existence table
    if report.relationship_existence:
        html_content += "<h2>Relationship Existence (All 32 Relationships)</h2>\n"
        html_content += _generate_relationship_existence_html(report.relationship_existence)
    
    # Add relationship coverage
    if report.relationship_coverage:
        html_content += "<h2>Relationship Coverage</h2>\n"
        html_content += _generate_relationship_coverage_html(report.relationship_coverage)
    
    # Add relationship tables
    html_content += "<h2>Relationship Properties (5 with properties)</h2>\n"
    for rel_type in sorted(report.relationship_results.keys()):
        results = report.relationship_results[rel_type]
        html_content += _generate_relationship_table_html(rel_type, results)

    # Add stub nodes section
    if report.stub_node_results:
        html_content += "<h2>Stub Nodes</h2>\n"
        html_content += _generate_stub_nodes_html(report.stub_node_results)
    
    # Add JavaScript for search
    html_content += """
        <script>
            function searchTable() {
                const input = document.getElementById('searchBox');
                const filter = input.value.toLowerCase();
                const sections = document.getElementsByClassName('entity-section');
                
                for (let section of sections) {
                    const entityName = section.querySelector('.entity-name').textContent.toLowerCase();
                    const table = section.querySelector('table');
                    const rows = table.getElementsByTagName('tr');
                    let sectionHasMatch = false;
                    
                    for (let i = 1; i < rows.length; i++) {
                        const row = rows[i];
                        const text = row.textContent.toLowerCase();
                        
                        if (text.includes(filter) || entityName.includes(filter)) {
                            row.style.display = '';
                            sectionHasMatch = true;
                        } else {
                            row.style.display = 'none';
                        }
                    }
                    
                    section.style.display = sectionHasMatch || filter === '' ? '' : 'none';
                }
            }
        </script>
    </div>
</body>
</html>
"""
    
    with open(output_path, 'w') as f:
        f.write(html_content)
    
    print(f"{Colors.GREEN}✓ HTML report saved to: {output_path}{Colors.RESET}")


def _generate_entity_table_html(entity_type: str, results: List[PropertyValidationResult]) -> str:
    """Generate HTML table for entity properties."""
    html = f'<div class="entity-section">\n'
    html += f'<div class="entity-name">{entity_type}</div>\n'
    html += '<table>\n<thead>\n<tr>\n'
    html += '<th>Property</th><th>Required</th><th>Total</th><th>Populated</th><th>Empty</th><th>%</th><th>Category</th>\n'
    html += '</tr>\n</thead>\n<tbody>\n'
    
    sorted_results = sorted(results, key=lambda r: (not r.is_required, r.category.value))
    
    for result in sorted_results:
        req_class = 'required-yes' if result.is_required else 'required-no'
        req_text = 'YES' if result.is_required else 'no'
        failure_badge = '<span class="failure-badge">FAILURE</span>' if result.is_required and result.category == PopulationCategory.EMPTY else ''
        
        html += '<tr>\n'
        html += f'<td>{result.property_name}{failure_badge}</td>\n'
        html += f'<td class="{req_class}">{req_text}</td>\n'
        html += f'<td>{result.total_count}</td>\n'
        html += f'<td>{result.populated_count}</td>\n'
        html += f'<td>{result.empty_count}</td>\n'
        html += f'<td>{result.population_percentage:.2f}%</td>\n'
        html += f'<td><span class="category-{result.category.value}">{result.category.value}</span></td>\n'
        html += '</tr>\n'
    
    html += '</tbody>\n</table>\n</div>\n'
    return html


def _generate_relationship_table_html(rel_type: str, results: List[PropertyValidationResult]) -> str:
    """Generate HTML table for relationship properties."""
    html = f'<div class="entity-section">\n'
    html += f'<div class="entity-name">{rel_type}</div>\n'
    html += '<table>\n<thead>\n<tr>\n'
    html += '<th>Property</th><th>Total</th><th>Populated</th><th>Empty</th><th>%</th><th>Category</th>\n'
    html += '</tr>\n</thead>\n<tbody>\n'
    
    sorted_results = sorted(results, key=lambda r: r.category.value)
    
    for result in sorted_results:
        html += '<tr>\n'
        html += f'<td>{result.property_name}</td>\n'
        html += f'<td>{result.total_count}</td>\n'
        html += f'<td>{result.populated_count}</td>\n'
        html += f'<td>{result.empty_count}</td>\n'
        html += f'<td>{result.population_percentage:.2f}%</td>\n'
        html += f'<td><span class="category-{result.category.value}">{result.category.value}</span></td>\n'
        html += '</tr>\n'
    
    html += '</tbody>\n</table>\n</div>\n'
    return html


def _generate_relationship_existence_html(relationship_existence: dict) -> str:
    """Generate HTML table for relationship existence with counts and directional checking."""
    html = '<div class="entity-section">\n'
    html += '<table>\n<thead>\n<tr>\n'
    html += '<th>Relationship</th><th>Count</th><th>Has Properties</th><th>Expected</th>'
    html += '<th>Directional</th><th>Reverse Rel</th><th>Reverse Count</th><th>Discrepancy</th>\n'
    html += '</tr>\n</thead>\n<tbody>\n'
    
    # Sort by relationship name
    for rel_type in sorted(relationship_existence.keys()):
        result = relationship_existence[rel_type]
        
        # Color code based on expected/unexpected
        row_class = '' if result.is_expected else 'style="background-color: #fff3cd;"'
        
        has_props = '✓' if result.has_properties else '—'
        is_expected = '✓' if result.is_expected else '✗ UNEXPECTED'
        if result.is_same_name_bidirectional:
            is_bidir = 'Undirected'
        else:
            is_bidir = '✓' if result.is_bidirectional else '—'
        
        reverse_rel = result.reverse_rel_type or '—'
        reverse_count = result.reverse_count
        if reverse_count is not None:
            reverse_count = str(reverse_count)
        else:
            reverse_count = '—'
        
        discrepancy = result.count_discrepancy
        if discrepancy is not None:
            if discrepancy == 0:
                discrepancy = '✓ Perfect'
            else:
                discrepancy = f'⚠️ {discrepancy}'
        else:
            discrepancy = '—'
        
        html += f'<tr {row_class}>\n'
        html += f'<td><strong>{result.rel_type}</strong></td>\n'
        html += f'<td>{result.total_count}</td>\n'
        html += f'<td>{has_props}</td>\n'
        html += f'<td>{is_expected}</td>\n'
        html += f'<td>{is_bidir}</td>\n'
        html += f'<td>{reverse_rel}</td>\n'
        html += f'<td>{reverse_count}</td>\n'
        html += f'<td>{discrepancy}</td>\n'
        html += '</tr>\n'
    
    html += '</tbody>\n</table>\n</div>\n'
    return html


def _generate_stub_nodes_html(stub_node_results: dict) -> str:
    """Generate HTML section for stub node detection results."""
    labels_with_stubs = {label: r for label, r in stub_node_results.items() if r.stub_count > 0}
    total_stubs = sum(r.stub_count for r in stub_node_results.values())

    html = '<div class="entity-section">\n'
    html += '<p>A <strong>stub node</strong> has only its <code>id</code> property set — '
    html += 'all other properties are absent. '
    html += 'The id format is <code>&lt;connector&gt;::&lt;entity_type&gt;::&lt;unique_id&gt;</code>.</p>\n'

    if total_stubs == 0:
        html += '<div style="background-color:#e8f5e9;padding:15px;border-radius:5px;margin:10px 0;">'
        html += f'<p style="color:#2e7d32;margin:0;"><strong>✓ No stub nodes found '
        html += f'across {len(stub_node_results)} labels</strong></p>'
        html += '</div>\n'
        html += '</div>\n'
        return html

    # Summary banner
    html += '<div style="background-color:#fff3cd;padding:15px;border-radius:5px;margin:10px 0;">'
    html += f'<p style="color:#856404;margin:0;"><strong>⚠️ {total_stubs} stub nodes found '
    html += f'in {len(labels_with_stubs)} label(s)</strong></p>'
    html += '</div>\n'

    for label, result in sorted(labels_with_stubs.items()):
        html += f'<div class="entity-name">{label}</div>\n'
        html += f'<p>{result.stub_count} / {result.total_count} nodes are stubs '
        html += f'({result.stub_percentage:.1f}%)</p>\n'

        if result.breakdown:
            html += '<table>\n<thead>\n<tr>\n'
            html += '<th>Connector</th><th>Entity Type</th><th>Stub Count</th>\n'
            html += '</tr>\n</thead>\n<tbody>\n'
            for b in result.breakdown:
                html += '<tr>\n'
                html += f'<td><code>{b.connector}</code></td>\n'
                html += f'<td><code>{b.entity_type}</code></td>\n'
                html += f'<td>{b.count}</td>\n'
                html += '</tr>\n'
            html += '</tbody>\n</table>\n'

        # Per-label Cypher query
        cypher = "\n".join([
            f"MATCH (n:{label})",
            "WHERE size(keys(n)) = 1 AND n.id IS NOT NULL",
            "RETURN labels(n) AS label, n.id AS id",
            "ORDER BY id",
        ])
        html += _cypher_block_html(f'Cypher — list all stub <strong>{label}</strong> nodes', cypher)

    # General query across all labels
    general_cypher = "\n".join([
        "MATCH (n)",
        "WHERE size(keys(n)) = 1 AND n.id IS NOT NULL",
        "WITH labels(n) AS label, n.id AS id",
        "RETURN label, id,",
        "       split(id, '::')[0] AS connector,",
        "       split(id, '::')[1] AS entity_type",
        "ORDER BY label, connector, entity_type, id",
    ])
    html += _cypher_block_html('Cypher — list ALL stub nodes (all labels)', general_cypher)

    html += '</div>\n'
    return html


def _cypher_block_html(title: str, query: str) -> str:
    """Render a labelled, copy-able Cypher code block."""
    escaped = query.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    # Escape newlines for the HTML data attribute so the JS copy button gets a clean string
    data_q = query.replace('&', '&amp;').replace('"', '&quot;').replace('\n', '&#10;')
    return (
        '<div style="margin:12px 0;">\n'
        f'<p style="margin:0 0 4px 0;font-size:0.9em;color:#555;">{title}</p>\n'
        '<div style="position:relative;">\n'
        '<pre style="background:#1e1e1e;color:#d4d4d4;padding:14px 16px;border-radius:4px;'
        'font-size:0.85em;overflow-x:auto;margin:0;">'
        f'<code>{escaped}</code></pre>\n'
        '<button onclick="navigator.clipboard.writeText(this.dataset.q)" '
        'style="position:absolute;top:6px;right:8px;background:#333;color:#ccc;'
        'border:1px solid #555;border-radius:3px;padding:2px 8px;font-size:0.75em;cursor:pointer;" '
        f'data-q="{data_q}">Copy</button>\n'
        '</div>\n'
        '</div>\n'
    )


def _generate_relationship_coverage_html(coverage: 'RelationshipCoverageResult') -> str:
    """Generate HTML for relationship coverage summary."""
    html = '<div class="entity-section">\n'
    
    # Calculate coverage percentage
    coverage_pct = (coverage.discovered_count / coverage.expected_count * 100) if coverage.expected_count > 0 else 0.0
    
    html += f'<p><strong>Expected:</strong> {coverage.expected_count} | '
    html += f'<strong>Discovered:</strong> {coverage.discovered_count} | '
    html += f'<strong>Coverage:</strong> {coverage_pct:.1f}%</p>\n'
    
    if coverage.missing_relationships:
        html += '<div style="background-color: #ffebee; padding: 15px; border-radius: 5px; margin: 10px 0;">\n'
        html += f'<h3 style="color: #c62828; margin-top: 0;">Missing Relationships ({len(coverage.missing_relationships)})</h3>\n'
        html += '<ul>\n'
        for rel in coverage.missing_relationships:
            html += f'<li><code>{rel}</code></li>\n'
        html += '</ul>\n</div>\n'
    
    if coverage.unexpected_relationships:
        html += '<div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 10px 0;">\n'
        html += f'<h3 style="color: #856404; margin-top: 0;">Unexpected Relationships ({len(coverage.unexpected_relationships)})</h3>\n'
        html += '<ul>\n'
        for rel in coverage.unexpected_relationships:
            html += f'<li><code>{rel}</code></li>\n'
        html += '</ul>\n</div>\n'
    
    if coverage.bidirectional_mismatches:
        html += '<div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 10px 0;">\n'
        html += f'<h3 style="color: #856404; margin-top: 0;">Directional Mismatches ({len(coverage.bidirectional_mismatches)})</h3>\n'
        html += '<ul>\n'
        for mismatch in coverage.bidirectional_mismatches:
            html += f'<li>{mismatch}</li>\n'
        html += '</ul>\n</div>\n'
    
    if not coverage.missing_relationships and not coverage.unexpected_relationships and not coverage.bidirectional_mismatches:
        html += '<div style="background-color: #e8f5e9; padding: 15px; border-radius: 5px; margin: 10px 0;">\n'
        html += '<p style="color: #2e7d32; margin: 0;"><strong>✓ All expected relationships present</strong></p>\n'
        html += '</div>\n'
    
    html += '</div>\n'
    return html
