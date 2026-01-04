import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback
import requests
import os

TIMEOUT_SECONDS = 30

def get_layout():
    """Return the chat page layout"""
    return html.Div([
        html.H2("AI Chat Assistant", className="mb-4"),
        
        # Chat container with messages
        dbc.Card([
            dbc.CardBody([
                html.Div(
                    id="chat-messages",
                    className="chat-messages-container",
                    style={
                        "height": "500px",
                        "overflowY": "auto",
                        "marginBottom": "20px",
                        "padding": "15px",
                        "backgroundColor": "#f8f9fa",
                        "borderRadius": "5px"
                    },
                    children=[
                        html.Div("Start a conversation by typing a message below.", 
                                className="text-muted text-center mt-5")
                    ]
                ),
                
                # Input area
                dbc.Row([
                    dbc.Col([
                        dbc.Textarea(
                            id="chat-input",
                            placeholder="Type your message here...",
                            style={"height": "80px"},
                            className="mb-2"
                        )
                    ], width=10),
                    dbc.Col([
                        dbc.Button(
                            "Send",
                            id="send-button",
                            color="primary",
                            className="w-100",
                            style={"height": "80px"}
                        )
                    ], width=2)
                ], className="g-2"),
                
                # Hidden div to store session_id (persists across page reloads)
                dcc.Store(id="session-store", storage_type="session"),
                
                # Loading spinner
                dcc.Loading(
                    id="loading-chat",
                    type="default",
                    children=html.Div(id="loading-output")
                )
            ])
        ], className="shadow-sm")
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
     Output("session-store", "data", allow_duplicate=True)],
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
        return render_messages(messages), "", session_data
    
    session_id = session_data.get("session_id")
    if not session_id:
        error_msg = session_data.get("error", "Unknown error")
        return [html.Div(f"Error: Could not create chat session. {error_msg}", 
                        className="alert alert-danger")], "", session_data
    
    # Get API base URL
    api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    # Add user message to history
    messages = session_data.get("messages", [])
    messages.append({"role": "user", "content": user_message})
    
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
                messages.append({"role": "error", "content": f"Session expired and failed to create new session: {str(retry_error)}"})
                session_data["messages"] = messages
                return render_messages(messages), "", session_data
        
        response.raise_for_status()
        data = response.json()
        
        # Add AI response to history
        messages.append({"role": "assistant", "content": data["ai_message"]})
        
        # Update session data
        session_data["messages"] = messages
        
        return render_messages(messages), "", session_data
        
    except requests.exceptions.HTTPError as e:
        # Add error message
        messages.append({"role": "error", "content": f"HTTP Error: {str(e)}"})
        session_data["messages"] = messages
        return render_messages(messages), "", session_data
    except Exception as e:
        # Add error message
        messages.append({"role": "error", "content": f"Error: {str(e)}"})
        session_data["messages"] = messages
        return render_messages(messages), "", session_data


def render_messages(messages):
    """Render the message history"""
    if not messages:
        return [html.Div("Start a conversation by typing a message below.", 
                        className="text-muted text-center mt-5")]
    
    rendered = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role == "user":
            rendered.append(
                dbc.Card([
                    dbc.CardBody([
                        html.Strong("You:", className="text-primary"),
                        html.Div(content, className="mt-2", style={"whiteSpace": "pre-wrap"})
                    ])
                ], className="mb-3 bg-light")
            )
        elif role == "assistant":
            rendered.append(
                dbc.Card([
                    dbc.CardBody([
                        html.Strong("AI Assistant:", className="text-success"),
                        html.Div(content, className="mt-2", style={"whiteSpace": "pre-wrap"})
                    ])
                ], className="mb-3 bg-white border-success")
            )
        elif role == "error":
            rendered.append(
                dbc.Alert(content, color="danger", className="mb-3")
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
