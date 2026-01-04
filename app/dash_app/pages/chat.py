import os
from datetime import datetime

import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, clientside_callback
import requests

TIMEOUT_SECONDS = 30

def get_layout():
    """Return the chat page layout"""
    return html.Div([
        html.H2("AI Chat Assistant", className="mb-4", style={"fontWeight": "600", "color": "#1a1a1a"}),
        
        # Chat container with messages
        html.Div([
            html.Div(
                id="chat-messages",
                className="chat-messages-container",
                style={
                    "height": "600px",
                    "overflowY": "auto",
                    "marginBottom": "20px",
                    "padding": "20px",
                    "backgroundColor": "#ffffff",
                    "borderRadius": "12px",
                    "border": "1px solid #e0e0e0",
                    "boxShadow": "0 2px 8px rgba(0,0,0,0.05)"
                },
                children=[
                    html.Div(
                        "👋 Welcome! Start a conversation by typing a message below.", 
                        className="text-center",
                        style={
                            "color": "#666",
                            "fontSize": "15px",
                            "marginTop": "100px",
                            "fontWeight": "400"
                        }
                    )
                ]
            ),
            
            # Input area - modern design
            html.Div([
                dbc.Row([
                    dbc.Col([
                        dbc.Textarea(
                            id="chat-input",
                            placeholder="Type your message here...",
                            style={
                                "height": "60px",
                                "borderRadius": "12px",
                                "border": "2px solid #e0e0e0",
                                "padding": "12px 16px",
                                "fontSize": "15px",
                                "resize": "none",
                                "transition": "border-color 0.2s"
                            },
                            className="mb-0"
                        )
                    ], width=10),
                    dbc.Col([
                        dbc.Button(
                            [html.I(className="fas fa-paper-plane me-2"), "Send"],
                            id="send-button",
                            color="primary",
                            className="w-100",
                            style={
                                "height": "60px",
                                "borderRadius": "12px",
                                "fontWeight": "500",
                                "fontSize": "15px",
                                "boxShadow": "0 2px 6px rgba(13, 110, 253, 0.25)"
                            }
                        )
                    ], width=2)
                ], className="g-2"),
            ], style={"padding": "0"}),
            
            # Hidden div to store session_id (persists across page reloads)
            dcc.Store(id="session-store", storage_type="session"),
            
            # Hidden div to trigger auto-scroll
            html.Div(id="scroll-trigger", style={"display": "none"}),
            
            # Loading spinner
            dcc.Loading(
                id="loading-chat",
                type="default",
                children=html.Div(id="loading-output")
            )
        ], style={
            "backgroundColor": "#f5f5f5",
            "padding": "24px",
            "borderRadius": "16px",
            "boxShadow": "0 4px 16px rgba(0,0,0,0.08)"
        })
    ], className="mt-4")


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
            # Try to send an empty test to validate session exists
            # If it fails with 404, we'll create a new session
            response = requests.post(
                f"{api_base}/api/v1/chats/{session_id}/messages",
                json={"message": "test"},
                timeout=TIMEOUT_SECONDS
            )
            # If we get here without exception, session is valid
            # But we don't want to actually process the test message
            # So we'll just return the existing data
            if response.status_code == 404:
                # Session doesn't exist, create new one
                print(f"Session {session_id} not found in backend, creating new session")
                current_data = None
            else:
                # Session exists, return current data
                return current_data
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
                messages.append({"role": "error", "content": f"Session expired and failed to create new session: {str(retry_error)}", "timestamp": datetime.now().strftime("%I:%M %p")})
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
        messages.append({"role": "error", "content": f"HTTP Error: {str(e)}", "timestamp": datetime.now().strftime("%I:%M %p")})
        session_data["messages"] = messages
        return render_messages(messages), "", session_data, str(n_clicks)
    except Exception as e:
        # Add error message
        messages.append({"role": "error", "content": f"Error: {str(e)}", "timestamp": datetime.now().strftime("%I:%M %p")})
        session_data["messages"] = messages
        return render_messages(messages), "", session_data, str(n_clicks)


def render_messages(messages):
    """Render the message history with modern chat bubbles"""
    if not messages:
        return [html.Div(
            "👋 Welcome! Start a conversation by typing a message below.", 
            className="text-center",
            style={
                "color": "#666",
                "fontSize": "15px",
                "marginTop": "100px",
                "fontWeight": "400"
            }
        )]
    
    rendered = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")
        
        if role == "user":
            # User message - right aligned with blue bubble
            rendered.append(
                html.Div([
                    html.Div([
                        html.Div([
                            html.Div(
                                content,
                                style={
                                    "backgroundColor": "#0d6efd",
                                    "color": "white",
                                    "padding": "12px 16px",
                                    "borderRadius": "18px 18px 4px 18px",
                                    "wordWrap": "break-word",
                                    "whiteSpace": "pre-wrap",
                                    "fontSize": "15px",
                                    "lineHeight": "1.5",
                                    "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
                                    "display": "inline-block"
                                }
                            ),
                            html.Div(
                                timestamp,
                                style={
                                    "fontSize": "11px",
                                    "color": "#999",
                                    "marginTop": "4px",
                                    "textAlign": "right"
                                }
                            )
                        ], style={"display": "inline-block", "textAlign": "right", "maxWidth": "70%"})
                    ], style={
                        "display": "flex",
                        "justifyContent": "flex-end",
                        "marginBottom": "16px",
                        "alignItems": "flex-end"
                    })
                ], style={"marginBottom": "8px"})
            )
        elif role == "assistant":
            # AI message - left aligned with gray bubble and avatar
            rendered.append(
                html.Div([
                    html.Div([
                        # Avatar
                        html.Div(
                            "🤖",
                            style={
                                "fontSize": "24px",
                                "marginRight": "12px",
                                "flexShrink": "0"
                            }
                        ),
                        html.Div([
                            html.Div(
                                content,
                                style={
                                    "backgroundColor": "#f0f0f0",
                                    "color": "#1a1a1a",
                                    "padding": "12px 16px",
                                    "borderRadius": "18px 18px 18px 4px",
                                    "wordWrap": "break-word",
                                    "whiteSpace": "pre-wrap",
                                    "fontSize": "15px",
                                    "lineHeight": "1.5",
                                    "boxShadow": "0 1px 2px rgba(0,0,0,0.05)",
                                    "display": "inline-block"
                                }
                            ),
                            html.Div(
                                timestamp,
                                style={
                                    "fontSize": "11px",
                                    "color": "#999",
                                    "marginTop": "4px",
                                    "textAlign": "left"
                                }
                            )
                        ], style={"display": "inline-block", "maxWidth": "70%"})
                    ], style={
                        "display": "flex",
                        "justifyContent": "flex-start",
                        "marginBottom": "16px",
                        "alignItems": "flex-end"
                    })
                ], style={"marginBottom": "8px"})
            )
        elif role == "error":
            # Error message - centered with red styling
            rendered.append(
                html.Div(
                    html.Div(
                        [html.I(className="fas fa-exclamation-circle me-2"), content],
                        style={
                            "backgroundColor": "#fee",
                            "color": "#c00",
                            "padding": "12px 16px",
                            "borderRadius": "8px",
                            "fontSize": "14px",
                            "border": "1px solid #fcc",
                            "textAlign": "center"
                        }
                    ),
                    style={"marginBottom": "16px"}
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
def submit_on_enter(n_submit, n_clicks):
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
