from services.modus import (
    check_occlusion as _check_occlusion,
)


def check_occlusion(occlusion_region, workspace=None):
    return _check_occlusion(occlusion_region, workspace)
