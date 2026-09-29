"""Single source of CLI defaults and provider configuration."""
from pathlib import Path
from runtime_paths import DEFAULT_STATE
HERE = Path(__file__).resolve().parent.parent
DEFAULT_CACHE = DEFAULT_STATE.parent / ".cache" / "find_nyaa_raw_cache.json"
DEFAULT_SCHEDULE_CACHE = DEFAULT_STATE.parent / ".cache" / "airing_schedule_cache.json"
DEFAULT_NICKNAME_ALIASES = HERE.parent / "references" / "anime_nickname_aliases.json"
ANILIST_API = "https://graphql.anilist.co"
BANGUMI_SEARCH_API = "https://api.bgm.tv/v0/search/subjects"
SCHEDULE_CACHE_VERSION = 7
SCHEDULE_CACHE_SECONDS = 30 * 60
MAINLINE_FORMATS = {"TV", "TV_SHORT", "ONA"}
MAINLINE_RELATION_TYPES = {"PREQUEL", "SEQUEL"}
CURRENT_NEW_ANIME_MAX_AGE_DAYS = 366
