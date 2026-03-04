import os
from datetime import datetime

import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, clientside_callback
import requests

from app.settings import settings

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT

def get_layout():
    """Return the chat page layout with Executive Dashboard aesthetic"""
    return html.Div([
        # Header with refined typography
        html.Div(
            "Strategic Analysis & Advisory",
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
        
        # Main chat container with refined styling
        html.Div([
            # Messages area with elegant container
            html.Div(
                id="chat-messages",
                className="chat-messages-container",
                style={
                    "height": "580px",
                    "overflowY": "auto",
                    "marginBottom": "24px",
                    "padding": "32px",
                    "backgroundColor": "#ffffff",
                    "borderRadius": "2px",
                    "border": "1px solid #cbd5e0",
                    "boxShadow": "0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02)"
                },
                children=[
                    html.Div([
                        html.Div(
                            "—",
                            style={
                                "fontFamily": "'Cormorant Garamond', serif",
                                "fontSize": "32px",
                                "color": "#2d3748",
                                "marginBottom": "16px"
                            }
                        ),
                        html.Div(
                            "Begin your strategic inquiry below. Each question will be analyzed with precision and depth.", 
                            style={
                                "fontFamily": "'Inter', sans-serif",
                                "color": "#4a5568",
                                "fontSize": "15px",
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
                                "fontFamily": "'Inter', sans-serif",
                                "height": "68px",
                                "borderRadius": "2px",
                                "border": "1px solid #cbd5e0",
                                "padding": "16px 20px",
                                "fontSize": "15px",
                                "resize": "none",
                                "transition": "all 0.2s ease",
                                "backgroundColor": "#ffffff",
                                "color": "#2d3748",
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
                                "fontFamily": "'Inter', sans-serif",
                                "height": "68px",
                                "borderRadius": "2px",
                                "fontWeight": "500",
                                "fontSize": "14px",
                                "letterSpacing": "0.5px",
                                "backgroundColor": "#2c5282",
                                "border": "none",
                                "transition": "all 0.2s ease",
                                "textTransform": "uppercase"
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
                color="#2c5282",
                children=html.Div(id="loading-output")
            )
        ], style={
            "backgroundColor": "#f7fafc",
            "padding": "24px",
            "borderRadius": "2px",
            "border": "1px solid #e2e8f0"
        })
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
                    "fontFamily": "'Cormorant Garamond', serif",
                    "fontSize": "32px",
                    "color": "#2d3748",
                    "marginBottom": "16px"
                }
            ),
            html.Div(
                "Begin your strategic inquiry below. Each question will be analyzed with precision and depth.", 
                style={
                    "fontFamily": "'Inter', sans-serif",
                    "color": "#4a5568",
                    "fontSize": "15px",
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
                                    "fontFamily": "'Inter', sans-serif",
                                    "backgroundColor": "#2c5282",
                                    "color": "#ffffff",
                                    "padding": "14px 20px",
                                    "borderRadius": "2px",
                                    "wordWrap": "break-word",
                                    "whiteSpace": "pre-wrap",
                                    "fontSize": "15px",
                                    "lineHeight": "1.7",
                                    "boxShadow": "0 1px 2px rgba(0,0,0,0.08)",
                                    "display": "inline-block",
                                    "borderLeft": "3px solid #1e3a5f"
                                }
                            ),
                            html.Div(
                                timestamp,
                                style={
                                    "fontFamily": "'Inter', sans-serif",
                                    "fontSize": "11px",
                                    "color": "#a0aec0",
                                    "marginTop": "6px",
                                    "textAlign": "right",
                                    "letterSpacing": "0.3px",
                                    "fontWeight": "500"
                                }
                            )
                        ], style={"display": "inline-block", "textAlign": "right", "maxWidth": "75%"})
                    ], style={
                        "display": "flex",
                        "justifyContent": "flex-end",
                        "marginBottom": "24px",
                        "alignItems": "flex-end"
                    })
                ], 
                className="chat-message-enter",
                style={"marginBottom": "8px"}
                )
            )
        elif role == "assistant":
            # AI message - refined left-aligned with elegant separator
            rendered.append(
                html.Div([
                    # Subtle divider before AI response
                    html.Div(
                        style={
                            "borderTop": "1px solid #e2e8f0",
                            "marginBottom": "20px",
                            "marginTop": "8px"
                        }
                    ),
                    html.Div([
                        # Icon/indicator
                        html.Div(
                            "◆",
                            style={
                                "fontFamily": "'Cormorant Garamond', serif",
                                "fontSize": "16px",
                                "color": "#2c5282",
                                "marginRight": "16px",
                                "marginTop": "4px",
                                "flexShrink": "0"
                            }
                        ),
                        html.Div([
                            html.Div(
                                content,
                                style={
                                    "fontFamily": "'Inter', sans-serif",
                                    "backgroundColor": "#ffffff",
                                    "color": "#2d3748",
                                    "padding": "16px 20px",
                                    "borderRadius": "2px",
                                    "wordWrap": "break-word",
                                    "whiteSpace": "pre-wrap",
                                    "fontSize": "15px",
                                    "lineHeight": "1.8",
                                    "display": "inline-block",
                                    "borderLeft": "2px solid #e2e8f0"
                                }
                            ),
                            html.Div(
                                timestamp,
                                style={
                                    "fontFamily": "'Inter', sans-serif",
                                    "fontSize": "11px",
                                    "color": "#a0aec0",
                                    "marginTop": "6px",
                                    "textAlign": "left",
                                    "letterSpacing": "0.3px",
                                    "fontWeight": "500"
                                }
                            )
                        ], style={"display": "inline-block", "maxWidth": "75%"})
                    ], style={
                        "display": "flex",
                        "justifyContent": "flex-start",
                        "marginBottom": "24px",
                        "alignItems": "flex-start"
                    })
                ], 
                className="chat-message-enter",
                style={"marginBottom": "16px"}
                )
            )
        elif role == "error":
            # Error message - refined and subtle
            rendered.append(
                html.Div(
                    html.Div(
                        [
                            html.Span("⚠", style={"marginRight": "8px", "fontSize": "14px"}),
                            html.Span(content)
                        ],
                        style={
                            "fontFamily": "'Inter', sans-serif",
                            "backgroundColor": "#fff5f5",
                            "color": "#c53030",
                            "padding": "12px 20px",
                            "borderRadius": "2px",
                            "fontSize": "14px",
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
