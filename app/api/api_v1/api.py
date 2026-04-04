"""
    This includes all the endpoints of the API Rest
"""
# pylint: disable=E0401,E0611

from fastapi import APIRouter

from .endpoints import play_music


router = APIRouter()
router.include_router(play_music.router,
                      prefix="/play_music", tags=["Music"])
