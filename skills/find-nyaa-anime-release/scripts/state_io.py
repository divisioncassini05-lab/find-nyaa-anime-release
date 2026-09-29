"""Legacy projection API; the repository owns persistence."""
import os
from anime_release.storage import StateFileError
from anime_release.repository import load as load_state, save_legacy as save_state, merge_legacy as merge_state
