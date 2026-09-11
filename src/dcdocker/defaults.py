"""Build defaults and source locations shared by the legacy entry points."""

DEFAULT_DC_CHAIN_PROFILE = "16.2.0"
KOS_REPOSITORY = "https://github.com/KallistiOS/KallistiOS.git"
KOS_TAGS_URL = "https://api.github.com/repos/maishuji/KallistiOS/git/refs/tags"
KOS_PORTS_TAGS_URL = "https://api.github.com/repos/maishuji/kos-ports/git/refs/tags"
GLDC_BRANCHES_URL = (
    "https://gitlab.com/api/v4/projects/quentin.cartier.dev%2FGLdc/repository/branches"
)
REQUEST_TIMEOUT = 30
SNAPSHOT_YEARS = ("2026", "2025", "master")
TOOLCHAIN_DOCKERFILE = "utils/kos-chain/docker/Dockerfile"
READY_CONTEXT_FILES = ("Dockerfile", "apk-retry.sh")
