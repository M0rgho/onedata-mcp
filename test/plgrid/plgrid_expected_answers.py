"""Hard-coded oracle values for PLGrid Forge Onedata E2E tests.

Tune these when the reference PLGrid tenant changes (spaces, files, harvesters).
"""

from __future__ import annotations

# list_user_spaces — full set the model should echo when asked to enumerate workspaces.
EXPECTED_LISTED_SPACE_NAMES: tuple[str, ...] = (
    "krk-p",
    "krk-iu",
    "openfoodfacts-images",
)

# krk-p / krk-iu recall scenarios
EXPECTED_KRK_SPACE_NAMES: frozenset[str] = frozenset({"krk-p", "krk-iu"})

# Logical path whose basename must round-trip via get_file_attributes (REG in krk-iu).
FILE_ATTRS_LOGICAL_PATH = "/krk-iu/bee_movie_script"
EXPECTED_FILE_BASENAME = "bee_movie_script"

# Bee movie size scenario (same object as FILE_ATTRS_LOGICAL_PATH).
BEE_MOVIE_LOGICAL_PATH = "/krk-iu/bee_movie_script"
EXPECTED_BEE_MOVIE_SIZE_BYTES = 49474

# query_harvester_index — reference harvester + index on the PLGrid tester account.
EXPECTED_HARVESTER_ID = "38aead36531afe751f19ee8dbc1de4d7chb7d6"
EXPECTED_HARVESTER_INDEX_ID = "df3a594999a498af355cf487e28fec59chdedf"
