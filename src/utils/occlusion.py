from services.modus import (
    check_occlusion as _check_occlusion,
    get_screen_dimensions as _get_screen_dimensions,
    get_active_workspace_id,
)


def get_current_workspace():
    return get_active_workspace_id()


def get_screen_dimensions():
    return _get_screen_dimensions()


def check_occlusion(occlusion_region, workspace=None):
    return _check_occlusion(occlusion_region, workspace)
