from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, ConfigDict


class ConnectorConfigUpdateRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None


class GithubConfigItemRequest(BaseModel):
    url: str
    access_token: Optional[str] = None
    search_filters: Optional[Dict[str, str]] = None
    branch_name_patterns: Optional[List[str]] = None
    extraction_sources: Optional[List[str]] = None
    enabled: bool = True


class JiraConfigItemRequest(BaseModel):
    url: str
    email: str
    api_token: Optional[str] = None
    enabled: bool = True


class SlackConfigItemRequest(BaseModel):
    channel_id: str
    channel_name: str
    enabled: bool = True


class TeamsConfigItemRequest(BaseModel):
    channel_id: str
    channel_name: str
    enabled: bool = True


class ConfluenceConfigItemRequest(BaseModel):
    space_key: str
    space_name: str
    enabled: bool = True


class GoogleDocsConfigItemRequest(BaseModel):
    drive_id: str
    drive_name: str
    enabled: bool = True


class SharepointConfigItemRequest(BaseModel):
    site_url: str
    enabled: bool = True


class EmailConfigItemRequest(BaseModel):
    smtp_host: str
    smtp_port: int
    imap_host: str
    imap_port: int
    username: str
    use_tls: bool
    password: Optional[str] = None
    enabled: bool = True


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
    search_filters: Optional[Dict[str, str]] = None
    branch_name_patterns: Optional[List[str]] = None
    extraction_sources: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class JiraConfigItem(BaseModel):
    id: int
    url: str
    email: str
    api_token: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class SlackConfigItem(BaseModel):
    id: int
    channel_id: str
    channel_name: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class TeamsConfigItem(BaseModel):
    id: int
    channel_id: str
    channel_name: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class ConfluenceConfigItem(BaseModel):
    id: int
    space_key: str
    space_name: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class GoogleDocsConfigItem(BaseModel):
    id: int
    drive_id: str
    drive_name: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class SharepointConfigItem(BaseModel):
    id: int
    site_url: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    enabled: bool

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
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
