"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from starlette.requests import Request

from app.content import LocaleContent
from app.core.config import Settings
from app.core.templating import Renderer


def get_settings_dep(request: Request) -> Settings:
    """Dependency: the application settings."""
    settings: Settings = request.app.state.settings
    return settings


def get_renderer(request: Request) -> Renderer:
    """Dependency: the template renderer."""
    renderer: Renderer = request.app.state.renderer
    return renderer


def get_content(request: Request) -> LocaleContent:
    """Dependency: the content in the language taken from the URL prefix."""
    content: LocaleContent = request.app.state.content.get(request.state.locale)
    return content


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
RendererDep = Annotated[Renderer, Depends(get_renderer)]
ContentDep = Annotated[LocaleContent, Depends(get_content)]
