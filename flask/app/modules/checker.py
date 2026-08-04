from ..core import core
from ..game_config import ADMINS
from .auth import current_identity


def is_admin() -> bool:
    identity = current_identity()
    if identity is None:
        return False

    _, team_admin = core.check_player(identity.username)
    return team_admin or (identity.username in ADMINS)


def is_player() -> bool:
    identity = current_identity()
    if identity is None:
        return False

    team, _ = core.check_player(identity.username)
    return (team is not None) or (identity.username in ADMINS)


def is_game_admin() -> bool:
    identity = current_identity()
    return identity is not None and identity.username in ADMINS
