import importlib

from gsuid_core.logger import logger

from ....utils.damage.abstract import DamageRankRegister, DamageDetailRegister

ID_MAPPING = {
    "1102": "1102",
    "1103": "1103",
    "1104": "1104",
    "1105": "1105",
    "1106": "1106",
    "1107": "1107",
    "1202": "1202",
    "1203": "1203",
    "1204": "1204",
    "1205": "1205",
    "1206": "1206",
    "1207": "1207",
    "1208": "1208",
    "1301": "1301",
    "1302": "1302",
    "1303": "1303",
    "1304": "1304",
    "1305": "1305",
    "1306": "1306",
    "1307": "1307",
    "1402": "1402",
    "1403": "1403",
    "1404": "1404",
    "1405": "1405",
    "1406": "1406",
    "1407": "1407",
    "1409": "1409",
    "1410": "1410",
    "1411": "1411",
    "1408": "1406",
    "1503": "1503",
    "1504": "1504",
    "1505": "1505",
    "1506": "1506",
    "1507": "1507",
    "1508": "1508",
    "1501": "1502",
    "1502": "1502",
    "1601": "1601",
    "1602": "1602",
    "1603": "1603",
    "1606": "1606",
    "1607": "1607",
    "1608": "1608",
    "1604": "1604",
    "1605": "1604",
}


def _dynamic_load_and_register(attr_name, register_cls, force_reload=False):
    current_globals = globals()
    for char_id, module_suffix in ID_MAPPING.items():
        module_path = f"..waves_build.damage_{module_suffix}"
        try:
            module = importlib.import_module(module_path, package=__package__)
            if force_reload:
                importlib.reload(module)
            if not hasattr(module, attr_name):
                continue

            target_obj = getattr(module, attr_name)
            register_cls.register_class(char_id, target_obj)
            global_var_name = f"{attr_name.split('_')[0]}_{char_id}"
            current_globals[global_var_name] = target_obj

        except ImportError:
            logger.warning(f"[Warning] 模块 {module_path} 未找到，请等待下载完成后再进行其他操作，除非遇到下载问题。")
        except Exception as e:
            logger.warning(f"[Warning] Failed to load {module_path} for {char_id}: {e}")


def register_damage(reload=False):
    _dynamic_load_and_register(attr_name="damage_detail", register_cls=DamageDetailRegister, force_reload=reload)


def register_rank(reload=False):
    _dynamic_load_and_register(attr_name="rank", register_cls=DamageRankRegister, force_reload=reload)


def reload_all_register():
    # 注册
    from ...queues import init_queues
    from ...damage.register_char import register_char
    from ...damage.register_echo import register_echo
    from ...damage.register_weapon import register_weapon

    register_weapon()
    register_echo()

    register_damage(reload=True)
    register_rank(reload=True)

    register_char()

    # 初始化任务队列
    init_queues()
