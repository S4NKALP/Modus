import sys
import os

# from hyprpy import Hyprland
from fabric.audio import Audio
from fabric.notifications import Notifications
from services.modus import ModusService
from loguru import logger


global modus_service
try:
    modus_service = ModusService()
except Exception as e:
    logger.error("[Main] Failed to create ModusService:", e)
    sys.exit(1)

# global notification_service
# try:
#    notification_service = Notifications()
# except Exception as e:
#    logger.error("[Main] Failed to create NotificationService:", e)
#    sys.exit(1)

global audio_service
try:
    audio_service = Audio()
except Exception as e:
    logger.error("[Main] Failed to create AudioService:", e)
    sys.exit(1)
