"""Build defaults and source locations shared by the legacy entry points."""

DEFAULT_DC_CHAIN_PROFILE = "16.2.0"
KOS_REPOSITORY = "https://github.com/KallistiOS/KallistiOS.git"
KOS_TAGS_URL = "https://api.github.com/repos/maishuji/KallistiOS/tags"
KOS_PORTS_TAGS_URL = "https://api.github.com/repos/maishuji/kos-ports/tags"
GLDC_BRANCHES_URL = (
    "https://gitlab.com/api/v4/projects/quentin.cartier.dev%2FGLdc/repository/branches"
)
REQUEST_TIMEOUT = 30
REF_PAGE_SIZE = 100
MAX_REF_PAGES = 20
TOOLCHAIN_PROFILES = "utils/kos-chain/profiles/dreamcast"
TOOLCHAIN_DOCKERFILE = "utils/kos-chain/docker/Dockerfile"
READY_CONTEXT_FILES = ("Dockerfile", "apk-retry.sh")
