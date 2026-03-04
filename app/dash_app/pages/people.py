from dash import html
import dash_bootstrap_components as dbc


def get_layout():
    """Return the people page layout with Executive Dashboard aesthetic"""
    return html.Div([
        # Header with refined typography
        html.Div(
            "Personnel & Organizational Structure",
            style={
                "fontFamily": "'Inter', sans-serif",
                "fontSize": "13px",
                "color": "#718096",
                "letterSpacing": "1.5px",
                "textTransform": "uppercase",
                "fontWeight": "500",
                "borderBottom": "1px solid #e2e8f0",
                "paddingBottom": "12px",
                "marginBottom": "16px"
            }
        ),
        
        # Main content container
        html.Div([
            # Placeholder message
            html.Div([
                html.Div(
                    "◆",
                    style={
                        "fontFamily": "'Cormorant Garamond', serif",
                        "fontSize": "32px",
                        "color": "#2c5282",
                        "marginBottom": "16px",
                        "textAlign": "center"
                    }
                ),
                html.Div(
                    "Team directory integration pending",
                    style={
                        "fontFamily": "'Inter', sans-serif",
                        "fontSize": "15px",
                        "color": "#4a5568",
                        "marginBottom": "24px",
                        "textAlign": "center",
                        "fontWeight": "400"
                    }
                ),
                html.Div(
                    "This module will provide comprehensive personnel oversight, including:",
                    style={
                        "fontFamily": "'Inter', sans-serif",
                        "fontSize": "14px",
                        "color": "#718096",
                        "marginBottom": "16px",
                        "lineHeight": "1.7"
                    }
                ),
            ], style={
                "maxWidth": "640px",
                "marginLeft": "auto",
                "marginRight": "auto",
                "marginBottom": "32px",
                "padding": "40px 32px",
                "backgroundColor": "#ffffff",
                "border": "1px solid #e2e8f0",
                "borderRadius": "2px"
            }),
            
            # Feature grid
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Div(
                            "Personnel Profiles",
                            style={
                                "fontFamily": "'Inter', sans-serif",
                                "fontSize": "14px",
                                "fontWeight": "600",
                                "color": "#2d3748",
                                "marginBottom": "8px",
                                "textTransform": "uppercase",
                                "letterSpacing": "0.5px"
                            }
                        ),
                        html.Div(
                            "Detailed team member information, roles, and expertise areas",
                            style={
                                "fontFamily": "'Inter', sans-serif",
                                "fontSize": "13px",
                                "color": "#718096",
                                "lineHeight": "1.6"
                            }
                        )
                    ], style={
                        "padding": "24px",
                        "backgroundColor": "#f7fafc",
                        "border": "1px solid #e2e8f0",
                        "borderLeft": "3px solid #2c5282",
                        "borderRadius": "2px"
                    })
                ], md=6, className="mb-3"),
                
                dbc.Col([
                    html.Div([
                        html.Div(
                            "Organizational Structure",
                            style={
                                "fontFamily": "'Inter', sans-serif",
                                "fontSize": "14px",
                                "fontWeight": "600",
                                "color": "#2d3748",
                                "marginBottom": "8px",
                                "textTransform": "uppercase",
                                "letterSpacing": "0.5px"
                            }
                        ),
                        html.Div(
                            "Reporting hierarchies, department assignments, and team composition",
                            style={
                                "fontFamily": "'Inter', sans-serif",
                                "fontSize": "13px",
                                "color": "#718096",
                                "lineHeight": "1.6"
                            }
                        )
                    ], style={
                        "padding": "24px",
                        "backgroundColor": "#f7fafc",
                        "border": "1px solid #e2e8f0",
                        "borderLeft": "3px solid #2c5282",
                        "borderRadius": "2px"
                    })
                ], md=6, className="mb-3"),
                
                dbc.Col([
                    html.Div([
                        html.Div(
                            "Contact Directory",
                            style={
                                "fontFamily": "'Inter', sans-serif",
                                "fontSize": "14px",
                                "fontWeight": "600",
                                "color": "#2d3748",
                                "marginBottom": "8px",
                                "textTransform": "uppercase",
                                "letterSpacing": "0.5px"
                            }
                        ),
                        html.Div(
                            "Email addresses, communication channels, and preferred contact methods",
                            style={
                                "fontFamily": "'Inter', sans-serif",
                                "fontSize": "13px",
                                "color": "#718096",
                                "lineHeight": "1.6"
                            }
                        )
                    ], style={
                        "padding": "24px",
                        "backgroundColor": "#f7fafc",
                        "border": "1px solid #e2e8f0",
                        "borderLeft": "3px solid #2c5282",
                        "borderRadius": "2px"
                    })
                ], md=6, className="mb-3"),
                
                dbc.Col([
                    html.Div([
                        html.Div(
                            "Availability & Capacity",
                            style={
                                "fontFamily": "'Inter', sans-serif",
                                "fontSize": "14px",
                                "fontWeight": "600",
                                "color": "#2d3748",
                                "marginBottom": "8px",
                                "textTransform": "uppercase",
                                "letterSpacing": "0.5px"
                            }
                        ),
                        html.Div(
                            "Current workload, availability status, and resource allocation metrics",
                            style={
                                "fontFamily": "'Inter', sans-serif",
                                "fontSize": "13px",
                                "color": "#718096",
                                "lineHeight": "1.6"
                            }
                        )
                    ], style={
                        "padding": "24px",
                        "backgroundColor": "#f7fafc",
                        "border": "1px solid #e2e8f0",
                        "borderLeft": "3px solid #2c5282",
                        "borderRadius": "2px"
                    })
                ], md=6, className="mb-3"),
            ])
        ], style={
            "backgroundColor": "#ffffff",
            "padding": "24px",
            "borderRadius": "2px",
            "border": "1px solid #e2e8f0"
        })
    ], className="mt-3")
