"""Pydantic models for NCP API."""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class ContainerInfo(BaseModel):
    name: str
    status: str
    ip: Optional[str] = None
    host_port: Optional[int] = None
    created_at: Optional[str] = None
    owner: Optional[str] = "unclaimed"


class ContainerCreateRequest(BaseModel):
    name: str
    port: int
    container_port: int = 80
    config: Optional[str] = None
    public: bool = False


class ProjectDeployRequest(BaseModel):
    files: Dict[str, str]


class ProjectDeployResponse(BaseModel):
    project: str
    containers: List[ContainerInfo]
    message: str


class ContainerDestroyRequest(BaseModel):
    name: str


class UserRegister(BaseModel):
    username: str
    password: str
    email: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
