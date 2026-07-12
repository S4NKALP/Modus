from fabric.audio import Audio
from .brightness import Brightness
from .network import NetworkClient
from .notification import *
from .powerprofile import *

network_client = NetworkClient()
brightness = Brightness()
audio = Audio()
notification_service = CustomNotifications()
