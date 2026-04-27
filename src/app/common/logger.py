import os
from datetime import datetime, timezone
import logging
import sys
import traceback
import json
import contextvars
import requests 


OUTPUT_DIR = os.getenv("OUTPUT_DIR", ".")
LOG_DIR = os.getenv("LOG_DIR", OUTPUT_DIR)
LOG_FORMAT = os.getenv("LOG_FORMAT", "JSON").upper()  # JSON or TEXT
start_time = datetime.now(tz=timezone.utc)
log_filename = os.path.join(LOG_DIR, f"logger_{start_time.strftime('%Y_%m_%d_%H_%M_%S')}.log")

# Define context variables
project_id_var = contextvars.ContextVar('project_id', default='')
user_id_var = contextvars.ContextVar('user_id', default='')
request_id_var = contextvars.ContextVar('request_id', default='')

# pylint: disable=too-many-instance-attributes
class LogContext:
    def __init__(self, project_id: str|None = None, 
                 user_id: str|None = None,
                 request_id: str|None = None) -> None:
        self.project_id = project_id
        self.user_id = user_id
        self.request_id = request_id
        self.project_id_token = None
        self.user_id_token = None
        self.request_id_token = None

    def __enter__(self):
        if self.project_id is not None:
            self.project_id_token = project_id_var.set(self.project_id)
        if self.user_id is not None:
            self.user_id_token = user_id_var.set(self.user_id)
        if self.request_id is not None:
            self.request_id_token = request_id_var.set(self.request_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.project_id_token is not None:
            project_id_var.reset(self.project_id_token)
        if self.user_id_token is not None:
            user_id_var.reset(self.user_id_token)
        if self.request_id_token is not None:
            request_id_var.reset(self.request_id_token)

class TextFormatter(logging.Formatter):
    def format(self, record):
        # Add context variables to the record
        record.project_id = project_id_var.get()
        record.user_id = user_id_var.get()
        record.request_id = request_id_var.get()
        
        # Only include context variables if they are set
        context_info = []
        if record.project_id: # type: ignore
            context_info.append(f"project_id={record.project_id}") # type: ignore
        if record.user_id:  # type: ignore
            context_info.append(f"user_id={record.user_id}") # type: ignore
        if record.request_id:  # type: ignore
            context_info.append(f"request_id={record.request_id}") # type: ignore
            
        context_str = " ".join(context_info)
        if context_str:
            context_str = f"[{context_str}] "
            
        # pylint: disable=protected-access
        self._style._fmt = f'[%(levelname)s] %(asctime)s {context_str}[%(filename)s:%(lineno)d] %(message)s'
        
        return super().format(record)

class JsonFormatter(logging.Formatter):
    def format(self, record):
        # Get the original format data
        log_data = {           
            'message': record.getMessage(),
            'location': f"{record.filename}:{record.lineno}",
            'level': record.levelname,
            'timestamp': self.formatTime(record),
        }
        
        # Add context variables if they exist
        if project_id_var.get():
            log_data['project_id'] = project_id_var.get()
        if user_id_var.get():
            log_data['user_id'] = user_id_var.get()
        if request_id_var.get():
            log_data['request_id'] = request_id_var.get()
            
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
            
        return json.dumps(log_data)

class SecopsLogger(logging.Logger):
    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name, level)
        self.slack_webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        self.slack_channel = os.getenv('SLACK_CHANNEL')
        self.slack_username = os.getenv("SLACK_USERNAME", "secops")
        
    def error(self, msg, *args, **kwargs):
        super().error(msg, *args, **kwargs)
        
        if isinstance(msg, Exception):
            error_message = str(msg)
            stack_trace = ''.join(traceback.format_exception(type(msg), msg, msg.__traceback__))
            if LOG_FORMAT == "JSON":
                value = json.dumps({
                    "error": error_message,
                    "stack_trace": stack_trace,
                    "project_id": project_id_var.get(),
                    "user_id": user_id_var.get(),
                    "request_id": request_id_var.get()
                })
            else:
                value = f"Error: {error_message}\n\nStack Trace:\n{stack_trace}"
        else:
            value = json.dumps(msg) if LOG_FORMAT == "JSON" else str(msg)
            
        if self.slack_webhook_url:
            try:
                payload = {
                    'channel': self.slack_channel,
                    'username': self.slack_username,
                    "text": "ERROR",
                    "attachments": [{
                        "color": "#FF0000",
                        "fields": [{
                            "title": "Error Log",
                            "value": value,
                            "short": False
                        }]
                    }]
                }
                headers = {'Content-Type': 'application/json'}
                requests.post(
                    self.slack_webhook_url,
                    data=json.dumps(payload),
                    headers=headers,
                    timeout=10
                )
            except Exception as e:
                super().error(f"Failed to send Slack notification: {e}")

                
if os.getenv("ENABLE_SLACK_NOTIFICATION") == '1':
    logging.setLoggerClass(SecopsLogger)

def get_formatter():
    if LOG_FORMAT == "JSON":
        return JsonFormatter()
    return TextFormatter()

# Replace the formatter creation with:
formatter = get_formatter()

log_level = logging.getLevelName(os.getenv("LOG_LEVEL", "INFO"))

# Create a stream handler for writing logs to STDOUT
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)

# Create a logger and add the handlers
logger = logging.getLogger("secops")
logger.setLevel(log_level)
logger.addHandler(stream_handler)

def set_log_filename(filename: str) -> None:
    global log_filename
    log_filename = filename

def get_log_filename() -> str:
    return log_filename

# Create a file handler for writing logs to a file
if os.getenv("ENABLE_FILE_LOGGING"):
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
        file_handler = logging.FileHandler(log_filename)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Error creating log file. Reason = {e}. Proceeding")

if __name__ == "__main__":
    with LogContext(project_id="123", user_id="456", request_id="req-789"):
        logger.info("This is an info message.")
        try:
            1 / 0
        except ZeroDivisionError as e:
            logger.exception(e)
