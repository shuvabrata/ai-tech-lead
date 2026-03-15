from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, ConfigDict


class ConnectorConfigUpdateRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None


class GithubConfigItemRequest(BaseModel):
    url: str
    access_token: Optional[str] = None
    branch_name_patterns: Optional[List[str]] = None
    extraction_sources: Optional[List[str]] = None


class JiraConfigItemRequest(BaseModel):
    url: str
    email: str
    api_token: Optional[str] = None


class SlackConfigItemRequest(BaseModel):
    channel_id: str
    channel_name: str


class TeamsConfigItemRequest(BaseModel):
    channel_id: str
    channel_name: str


class ConfluenceConfigItemRequest(BaseModel):
    space_key: str
    space_name: str


class GoogleDocsConfigItemRequest(BaseModel):
    drive_id: str
    drive_name: str


class SharepointConfigItemRequest(BaseModel):
    site_url: str


class EmailConfigItemRequest(BaseModel):
    smtp_host: str
    smtp_port: int
    imap_host: str
    imap_port: int
    username: str
    use_tls: bool
    password: Optional[str] = None


class ConnectorStatus(BaseModel):
    connector_type: str
    display_name: str
    status: str
    enabled: bool
    config: Optional[Dict[str, Any]] = None
    last_tested_at: Optional[datetime] = None
    last_test_error: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class GithubConfigItem(BaseModel):
    id: int
    url: str
    access_token: Optional[str] = None
    branch_name_patterns: Optional[List[str]] = None
    extraction_sources: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


class JiraConfigItem(BaseModel):
    id: int
    url: str
    email: str
    api_token: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SlackConfigItem(BaseModel):
    id: int
    channel_id: str
    channel_name: str

    model_config = ConfigDict(from_attributes=True)


class TeamsConfigItem(BaseModel):
    id: int
    channel_id: str
    channel_name: str

    model_config = ConfigDict(from_attributes=True)


class ConfluenceConfigItem(BaseModel):
    id: int
    space_key: str
    space_name: str

    model_config = ConfigDict(from_attributes=True)


class GoogleDocsConfigItem(BaseModel):
    id: int
    drive_id: str
    drive_name: str

    model_config = ConfigDict(from_attributes=True)


class SharepointConfigItem(BaseModel):
    id: int
    site_url: str

    model_config = ConfigDict(from_attributes=True)


class EmailConfigItem(BaseModel):
    id: int
    smtp_host: str
    smtp_port: int
    imap_host: str
    imap_port: int
    username: str
    use_tls: bool
    password: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
