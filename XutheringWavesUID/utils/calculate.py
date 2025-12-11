from typing import Any, Dict, Tuple


def calc_phantom_entry(*args, **kwargs) -> Tuple[float, float]:
    from .waves_build.calculate import calc_phantom_entry as _func

    return _func(*args, **kwargs)


def calc_phantom_score(*args, **kwargs) -> Tuple[float, str]:
    from .waves_build.calculate import calc_phantom_score as _func

    return _func(*args, **kwargs)


def get_calc_map(*args, **kwargs) -> Dict:
    from .waves_build.calculate import get_calc_map as _func

    return _func(*args, **kwargs)


def get_max_score(*args, **kwargs) -> Tuple[float, Any]:
    from .waves_build.calculate import get_max_score as _func

    return _func(*args, **kwargs)


def get_total_score_bg(*args, **kwargs) -> str:
    from .waves_build.calculate import get_total_score_bg as _func

    return _func(*args, **kwargs)


def get_valid_color(*args, **kwargs) -> Tuple[str, str]:
    from .waves_build.calculate import get_valid_color as _func

    return _func(*args, **kwargs)
