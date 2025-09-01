from loguru import logger

from fabric.audio import Audio

from services.modus import ModusService, notification_service as notification_service_instance

global modus_service
try:
    modus_service = ModusService()
except Exception as e:
    logger.error(f"[Main] Failed to create ModusService: {e}")
    modus_service = None

if modus_service is None:
    logger.warning(
        "[Main] ModusService was not initialized. Functionality may be limited."
    )

global notification_service
try:
    notification_service = notification_service_instance
except Exception as e:
    logger.error(f"[Main] Failed to create NotificationService: {e}")
    notification_service = None

if notification_service is None:
    logger.warning(
        "[Main] NotificationService was not initialized. Notifications may not work."
    )

global audio_service
try:
    audio_service = Audio()
except Exception as e:
    logger.error(f"[Main] Failed to create AudioService: {e}")
    audio_service = None

if audio_service is None:
    logger.warning(
        "[Main] AudioService was not initialized. Audio features may not work."
    )
