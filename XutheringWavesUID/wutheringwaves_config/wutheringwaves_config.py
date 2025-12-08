from gsuid_core.utils.plugins_config.gs_config import StringConfig

from .show_config import SHOW_CONIFG
from .config_default import CONFIG_DEFAULT
from ..utils.resource.RESOURCE_PATH import MAIN_PATH, CONFIG_PATH

WutheringWavesConfig = StringConfig(
    "XutheringWavesUID",
    CONFIG_PATH,
    CONFIG_DEFAULT,
)

ShowConfig = StringConfig(
    "鸣潮展示配置",
    MAIN_PATH / "show_config.json",
    SHOW_CONIFG,
)
