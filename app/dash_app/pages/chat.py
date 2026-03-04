import os
from datetime import datetime

import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, clientside_callback
import requests

from app.settings import settings
from app.dash_app.components.common import create_page_header, create_diamond_icon
from app.dash_app.styles import (
    FONT_SANS,
    FONT_SERIF,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_LARGE,
    FONT_WEIGHT_MEDIUM,
    COLOR_NAVY,
    COLOR_NAVY_DARK,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_GRAY_DARK,
    COLOR_GRAY_LIGHT,
    COLOR_GRAY_LIGHTER,
    COLOR_BACKGROUND_WHITE,
    COLOR_BORDER,
    COLOR_ERROR,
    SPACING_XXXSMALL,
    SPACING_XXSMALL,
    SPACING_XSMALL,
    SPACING_SMALL,
    SPACING_MEDIUM,
    SPACING_LARGE,
    CARD_CONTAINER_STYLE,
    BUTTON_PRIMARY_STYLE
)

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT

def get_layout():
    """Return the chat page layout with Executive Dashboard aesthetic"""
    return html.Div([
        # Page header
        create_page_header("Strategic Analysis & Advisory"),
        
        # Main chat container with refined styling
        html.Div([
            # Messages area with elegant container
            html.Div(
                id="chat-messages",
                className="chat-messages-container",
                style={
                    "height": "580px",
                    "overflowY": "auto",
                    "marginBottom": SPACING_MEDIUM,
                    "padding": SPACING_LARGE,
                    "backgroundColor": COLOR_BACKGROUND_WHITE,
                    "borderRadius": "2px",
                    "border": f"1px solid {COLOR_GRAY_LIGHTER}",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02)"
                },
                children=[
                    html.Div([
                        html.Div(
                            "—",
                            style={
                                "fontFamily": FONT_SERIF,
                                "fontSize": "32px",
                                "color": COLOR_CHARCOAL_MEDIUM,
                                "marginBottom": SPACING_SMALL
                            }
                        ),
                        html.Div(
                            "Begin your strategic inquiry below. Each question will be analyzed with precision and depth.", 
                            style={
                                "fontFamily": FONT_SANS,
                                "color": COLOR_GRAY_DARK,
                                "fontSize": FONT_SIZE_LARGE,
                                "lineHeight": "1.7",
                                "fontWeight": "400"
                            }
                        )
                    ], 
                    className="text-center",
                    style={
                        "marginTop": "120px",
                        "maxWidth": "480px",
                        "marginLeft": "auto",
                        "marginRight": "auto"
                    })
                ]
            ),
            
            # Input area with sophisticated styling
            html.Div([
                dbc.Row([
                    dbc.Col([
                        dbc.Textarea(
                            id="chat-input",
                            placeholder="Compose your inquiry...",
                            style={
                                "fontFamily": FONT_SANS,
                                "height": "68px",
                                "borderRadius": "2px",
                                "border": f"1px solid {COLOR_GRAY_LIGHTER}",
                                "padding": f"{SPACING_SMALL} 20px",
                                "fontSize": FONT_SIZE_LARGE,
                                "resize": "none",
                                "transition": "all 0.2s ease",
                                "backgroundColor": COLOR_BACKGROUND_WHITE,
                                "color": COLOR_CHARCOAL_MEDIUM,
                                "lineHeight": "1.6"
                            },
                            className="mb-0 chat-input-refined"
                        )
                    ], width=10),
                    dbc.Col([
                        dbc.Button(
                            "Submit",
                            id="send-button",
                            className="w-100",
                            style={
                                **BUTTON_PRIMARY_STYLE,
                                "height": "68px"
                            }
                        )
                    ], width=2)
                ], className="g-3"),
            ], style={"padding": "0"}),
            
            # Hidden stores and triggers
            dcc.Store(id="session-store", storage_type="session"),
            html.Div(id="scroll-trigger", style={"display": "none"}),
            
            # Refined loading indicator
            dcc.Loading(
                id="loading-chat",
                type="circle",
                color=COLOR_NAVY,
                children=html.Div(id="loading-output")
            )
        ], style=CARD_CONTAINER_STYLE)
    ], className="mt-3")


# Callback to initialize chat session
@callback(
    Output("session-store", "data"),
    Input("session-store", "data")
)
def initialize_session(current_data):
    """Initialize a new chat session if one doesn't exist or is invalid"""
    api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    # If we have existing data, validate the session still exists in backend
    if current_data is not None and current_data.get("session_id"):
        session_id = current_data["session_id"]
        try:
            # Use GET endpoint to check if session exists (doesn't send messages)
            response = requests.get(
                f"{api_base}/api/v1/chats/{session_id}",
                timeout=TIMEOUT_SECONDS
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("exists"):
                # Session exists, return current data
                return current_data
            else:
                # Session doesn't exist, create new one
                print(f"Session {session_id} not found in backend, creating new session")
                current_data = None
        except requests.exceptions.RequestException:
            # If any error, treat as invalid session and create new one
            print("Session validation failed, creating new session")
            current_data = None
    
    # Create new session if current_data is None or validation failed
    if current_data is None:
        try:
            response = requests.post(
                f"{api_base}/api/v1/chats",
                json={"system_prompt": "You are a helpful AI technical assistant."},
                timeout=TIMEOUT_SECONDS
            )
            response.raise_for_status()
            data = response.json()
            return {"session_id": data["session_id"], "messages": []}
        except Exception as e:
            print(f"Error creating chat session: {e}")
            return {"session_id": None, "messages": [], "error": str(e)}
    
    return current_data


# Callback to send message and update chat
@callback(
    [Output("chat-messages", "children"),
     Output("chat-input", "value"),
     Output("session-store", "data", allow_duplicate=True),
     Output("scroll-trigger", "children")],
    [Input("send-button", "n_clicks")],
    [State("chat-input", "value"),
     State("session-store", "data")],
    prevent_initial_call=True
)
def send_message(n_clicks, user_message, session_data):
    """Send a message to the chat API and update the display"""
    if not user_message or not user_message.strip():
        # Return current state if no message
        messages = session_data.get("messages", [])
        return render_messages(messages), "", session_data, ""
    
    session_id = session_data.get("session_id")
    if not session_id:
        error_msg = session_data.get("error", "Unknown error")
        return [html.Div(f"Error: Could not create chat session. {error_msg}", 
                        className="alert alert-danger")], "", session_data, ""
    
    # Get API base URL
    api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    # Add user message to history with timestamp
    messages = session_data.get("messages", [])
    timestamp = datetime.now().strftime("%I:%M %p")
    messages.append({"role": "user", "content": user_message, "timestamp": timestamp})
    
    try:
        # Send message to API
        response = requests.post(
            f"{api_base}/api/v1/chats/{session_id}/messages",
            json={"message": user_message},
            timeout=TIMEOUT_SECONDS
        )
        
        # If session not found (404), create new session and retry
        if response.status_code == 404:
            try:
                # Create new session
                new_session_response = requests.post(
                    f"{api_base}/api/v1/chats",
                    json={"system_prompt": "You are a helpful AI technical assistant."},
                    timeout=TIMEOUT_SECONDS
                )
                new_session_response.raise_for_status()
                new_session_data = new_session_response.json()
                session_id = new_session_data["session_id"]
                
                # Update session data with new session_id and clear old messages
                session_data["session_id"] = session_id
                messages = [{"role": "user", "content": user_message}]  # Reset with current message
                
                # Retry sending message with new session
                response = requests.post(
                    f"{api_base}/api/v1/chats/{session_id}/messages",
                    json={"message": user_message},
                    timeout=TIMEOUT_SECONDS
                )
                response.raise_for_status()
            except Exception as retry_error:
                messages.append({
                    "role": "error",
                    "content": f"Session expired and failed to create new session: {str(retry_error)}",
                    "timestamp": datetime.now().strftime("%I:%M %p")
                })
                session_data["messages"] = messages
                return render_messages(messages), "", session_data, str(n_clicks)
        
        response.raise_for_status()
        data = response.json()
        
        # Add AI response to history with timestamp
        ai_timestamp = datetime.now().strftime("%I:%M %p")
        messages.append({"role": "assistant", "content": data["ai_message"], "timestamp": ai_timestamp})
        
        # Update session data
        session_data["messages"] = messages
        
        return render_messages(messages), "", session_data, str(n_clicks)
        
    except requests.exceptions.HTTPError as e:
        # Add error message
        messages.append({
            "role": "error",
            "content": f"HTTP Error: {str(e)}",
            "timestamp": datetime.now().strftime("%I:%M %p")
        })
        session_data["messages"] = messages
        return render_messages(messages), "", session_data, str(n_clicks)
    except Exception as e:
        # Add error message
        messages.append({
            "role": "error",
            "content": f"Error: {str(e)}",
            "timestamp": datetime.now().strftime("%I:%M %p")
        })
        session_data["messages"] = messages
        return render_messages(messages), "", session_data, str(n_clicks)


def render_messages(messages):
    """Render the message history with Executive Dashboard aesthetic"""
    if not messages:
        return [html.Div([
            html.Div(
                "—",
                style={
                    "fontFamily": FONT_SERIF,
                    "fontSize": "32px",
                    "color": COLOR_CHARCOAL_MEDIUM,
                    "marginBottom": SPACING_SMALL
                }
            ),
            html.Div(
                "Begin your strategic inquiry below. Each question will be analyzed with precision and depth.", 
                style={
                    "fontFamily": FONT_SANS,
                    "color": COLOR_GRAY_DARK,
                    "fontSize": FONT_SIZE_LARGE,
                    "lineHeight": "1.7",
                    "fontWeight": "400"
                }
            )
        ], 
        className="text-center",
        style={
            "marginTop": "120px",
            "maxWidth": "480px",
            "marginLeft": "auto",
            "marginRight": "auto"
        })]
    
    rendered = []
    for idx, msg in enumerate(messages):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")
        
        if role == "user":
            # User message - refined right-aligned design
            rendered.append(
                html.Div([
                    html.Div([
                        html.Div([
                            html.Div(
                                content,
                                style={
                                    "fontFamily": FONT_SANS,
                                    "backgroundColor": COLOR_NAVY,
                                    "color": COLOR_BACKGROUND_WHITE,
                                    "padding": "14px 20px",
                                    "borderRadius": "2px",
                                    "wordWrap": "break-word",
                                    "whiteSpace": "pre-wrap",
                                    "fontSize": FONT_SIZE_LARGE,
                                    "lineHeight": "1.7",
                                    "boxShadow": "0 1px 2px rgba(0,0,0,0.08)",
                                    "display": "inline-block",
                                    "borderLeft": f"3px solid {COLOR_NAVY_DARK}"
                                }
                            ),
                            html.Div(
                                timestamp,
                                style={
                                    "fontFamily": FONT_SANS,
                                    "fontSize": "11px",
                                    "color": COLOR_GRAY_LIGHT,
                                    "marginTop": SPACING_XXSMALL,
                                    "textAlign": "right",
                                    "letterSpacing": "0.3px",
                                    "fontWeight": FONT_WEIGHT_MEDIUM
                                }
                            )
                        ], style={"display": "inline-block", "textAlign": "right", "maxWidth": "75%"})
                    ], style={
                        "display": "flex",
                        "justifyContent": "flex-end",
                        "marginBottom": SPACING_MEDIUM,
                        "alignItems": "flex-end"
                    })
                ], 
                className="chat-message-enter",
                style={"marginBottom": SPACING_XXSMALL}
                )
            )
        elif role == "assistant":
            # AI message - refined left-aligned with elegant separator
            rendered.append(
                html.Div([
                    # Subtle divider before AI response
                    html.Div(
                        style={
                            "borderTop": f"1px solid {COLOR_BORDER}",
                            "marginBottom": "20px",
                            "marginTop": SPACING_XXSMALL
                        }
                    ),
                    html.Div([
                        # Icon/indicator
                        html.Div(
                            [create_diamond_icon()],
                            style={
                                "fontSize": "16px",
                                "marginRight": SPACING_SMALL,
                                "marginTop": SPACING_XXXSMALL,
                                "flexShrink": "0"
                            }
                        ),
                        html.Div([
                            html.Div(
                                content,
                                style={
                                    "fontFamily": FONT_SANS,
                                    "backgroundColor": COLOR_BACKGROUND_WHITE,
                                    "color": COLOR_CHARCOAL_MEDIUM,
                                    "padding": f"{SPACING_SMALL} 20px",
                                    "borderRadius": "2px",
                                    "wordWrap": "break-word",
                                    "whiteSpace": "pre-wrap",
                                    "fontSize": FONT_SIZE_LARGE,
                                    "lineHeight": "1.8",
                                    "display": "inline-block",
                                    "borderLeft": f"2px solid {COLOR_BORDER}"
                                }
                            ),
                            html.Div(
                                timestamp,
                                style={
                                    "fontFamily": FONT_SANS,
                                    "fontSize": "11px",
                                    "color": COLOR_GRAY_LIGHT,
                                    "marginTop": SPACING_XXSMALL,
                                    "textAlign": "left",
                                    "letterSpacing": "0.3px",
                                    "fontWeight": FONT_WEIGHT_MEDIUM
                                }
                            )
                        ], style={"display": "inline-block", "maxWidth": "75%"})
                    ], style={
                        "display": "flex",
                        "justifyContent": "flex-start",
                        "marginBottom": SPACING_MEDIUM,
                        "alignItems": "flex-start"
                    })
                ], 
                className="chat-message-enter",
                style={"marginBottom": SPACING_SMALL}
                )
            )
        elif role == "error":
            # Error message - refined and subtle
            rendered.append(
                html.Div(
                    html.Div(
                        [
                            html.Span("⚠", style={"marginRight": SPACING_XXSMALL, "fontSize": FONT_SIZE_MEDIUM}),
                            html.Span(content)
                        ],
                        style={
                            "fontFamily": FONT_SANS,
                            "backgroundColor": "#fff5f5",
                            "color": COLOR_ERROR,
                            "padding": f"{SPACING_XSMALL} 20px",
                            "borderRadius": "2px",
                            "fontSize": FONT_SIZE_MEDIUM,
                            "border": "1px solid #feb2b2",
                            "borderLeft": "3px solid #fc8181",
                            "textAlign": "left",
                            "lineHeight": "1.6"
                        }
                    ),
                    style={"marginBottom": "20px"}
                )
            )
    
    return rendered


# Optional: Callback to handle Enter key in textarea
@callback(
    Output("send-button", "n_clicks"),
    Input("chat-input", "n_submit"),
    State("send-button", "n_clicks"),
    prevent_initial_call=True
)
def submit_on_enter(_n_submit, n_clicks):
    """Trigger send button when Enter is pressed"""
    return (n_clicks or 0) + 1


# Clientside callback for auto-scrolling to bottom
clientside_callback(
    """
    function(trigger) {
        if (trigger) {
            setTimeout(function() {
                var chatContainer = document.querySelector('.chat-messages-container');
                if (chatContainer) {
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }
            }, 100);
        }
        return '';
    }
    """,
    Output("loading-output", "children"),
    Input("scroll-trigger", "children")
)
