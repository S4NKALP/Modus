from fabric.audio import Audio
from .brightness import Brightness
from .network import NetworkClient
from .battery import *

network_client = NetworkClient()
brightness = Brightness()
audio = Audio()

