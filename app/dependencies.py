from pathlib import Path

from fastapi import Request
from idu_service_auth import KeycloakTokenClient
from iduconfig import Config

from app.common.chat_storage.chat_storage_client import ChatStorageClient
from app.common.llm.chat_client import ChatClient
from app.gen_planner.gen_planner_service import GenPlannerService


def get_config(request: Request) -> Config:

    return request.app.state.config


def get_genplanner_service(request: Request, test: bool = False) -> GenPlannerService:
    if test:
        return request.app.state.test_genplanner_service
    return request.app.state.genplanner_service


def get_log_path(request: Request) -> Path:
    return request.app.state.log_path


def get_llm_chat_client(request: Request) -> ChatClient | None:
    return request.app.state.llm_chat_client


def get_chat_storage_client(request: Request) -> ChatStorageClient | None:
    return request.app.state.chat_storage_client


def get_keycloak_token_client(request: Request) -> KeycloakTokenClient | None:
    return request.app.state.keycloak_token_client
