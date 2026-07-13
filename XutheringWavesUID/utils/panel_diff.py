"""面板刷新 Diff 计算与渲染 — 适配插件真实数据结构。

数据格式: RoleDetailData (rawData.json 中的单条), 字段:
  - role: {roleId, roleName, level, attributeName, ...}
  - level: int (角色等级)
  - chainList: [{order, name, unlocked, ...}]
  - weaponData: {level, resonLevel, breach, weapon: {...}, mainPropList: [...]}
  - phantomData: {cost, equipPhantomList: [...]}
  - equipPhantomAddPropList: [{attributeName, attributeValue}]  ← 面板总属性
  - equipPhantomAttributeList: [{attributeName, attributeValue, key, valid}]
  - skillList, activeBranchId, skillBranchList, roleAttributeList, roleSkin
"""
from __future__ import annotations

import base64
import re
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from gsuid_core.logger import logger

from ..utils.resource.RESOURCE_PATH import PHANTOM_PATH
from ..utils.score import get_panel_score_grade

# ── 属性图标 ──────────────────────────────────────────────────────────────────

_ATTR_ICON_DIR = Path(__file__).parent / "texture2d" / "attribute_prop"
_PANEL_SCORE_DIR = Path(__file__).parent.parent / "wutheringwaves_charinfo" / "texture2d"
_CARD_BG_PATH = Path(__file__).parent / "texture2d" / "bg3.jpg"

_attr_icon_cache: Dict[str, str] = {}
_score_icon_cache: Dict[str, str] = {}
_phantom_icon_cache: Dict[str, str] = {}
_card_bg_b64: str = ""


def get_card_bg_b64() -> str:
    """获取面板自定义背景 base64 (与 PIL get_card_bg 同源逻辑)."""
    global _card_bg_b64
    if _card_bg_b64:
        return _card_bg_b64
    try:
        from ..wutheringwaves_config.wutheringwaves_config import ShowConfig
        bg_path = None
        if ShowConfig.get_config("CardBg").data:
            _p = Path(ShowConfig.get_config("CardBgPath").data)
            if _p.is_file():
                bg_path = _p
        if not bg_path:
            bg_path = _CARD_BG_PATH
        if bg_path.exists():
            with open(bg_path, "rb") as fh:
                _card_bg_b64 = base64.b64encode(fh.read()).decode()
            return _card_bg_b64
    except Exception as _e:
        logger.warning(f"[鸣潮·面板diff] 加载背景失败: {_e}")
    return ""


def _load_attr_icon(name: str) -> str:
    if name in _attr_icon_cache:
        return _attr_icon_cache[name]
    f = _ATTR_ICON_DIR / f"attr_prop_{name}.png"
    if f.exists():
        with open(f, "rb") as fh:
            _attr_icon_cache[name] = base64.b64encode(fh.read()).decode()
        return _attr_icon_cache[name]
    # fallback
    for k, v in _attr_icon_cache.items():
        if k in name or name in k:
            return v
    return ""


def _load_score_icon(grade: str) -> str:
    if grade in _score_icon_cache:
        return _score_icon_cache[grade]
    f = _PANEL_SCORE_DIR / f"panel_score_{grade}.png"
    if f.exists():
        with open(f, "rb") as fh:
            _score_icon_cache[grade] = base64.b64encode(fh.read()).decode()
        return _score_icon_cache[grade]
    return ""


def attr_icon_url(attr_name: str) -> str:
    b64 = _load_attr_icon(attr_name)
    return f"data:image/png;base64,{b64}" if b64 else ""


def score_icon_url(grade: str, size: int = 40) -> str:
    b64 = _load_score_icon(grade)
    if not b64:
        return ""
    return f'<img class="grade-icon-img" src="data:image/png;base64,{b64}" width="{size}" height="{size}">'


# ── 声骸图标 ──────────────────────────────────────────────────────────────────

def _get_local_phantom_b64(phantom_id: int) -> str:
    """从本地缓存加载声骸图标 base64, 找不到返回空."""
    if str(phantom_id) in _phantom_icon_cache:
        return _phantom_icon_cache[str(phantom_id)]
    f = PHANTOM_PATH / f"phantom_{phantom_id}.png"
    if not f.exists():
        f = PHANTOM_PATH / "phantom_390070051.png"
    if not f.exists():
        return ""
    with open(f, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    _phantom_icon_cache[str(phantom_id)] = b64
    return b64


def get_phantom_icon_url(phantom_prop: Dict) -> str:
    """获取声骸图标 URL: 优先本地 base64, 否则用 network iconUrl."""
    pid = phantom_prop.get("phantomId", 0)
    local_b64 = _get_local_phantom_b64(pid)
    if local_b64:
        return f"data:image/png;base64,{local_b64}"
    network_url = phantom_prop.get("iconUrl", "")
    return network_url


# ── 评分计算 ─────────────────────────────────────────────────────────────────

def compute_panel_score(char_data: Dict) -> Dict[str, float]:
    """计算单个角色的综合评分 + 声骸总分, 并附带每个声骸的单独评分。"""
    try:
        from ..utils.api.model import RoleDetailData
        from ..utils.calc import WuWaCalc
        from ..utils.calculate import calc_phantom_score, get_calc_map
        from ..utils.damage.modal import get_role_modal
        from ..utils.damage.abstract import ScoreDetailRegister

        role_detail = RoleDetailData(**char_data) if isinstance(char_data, dict) else char_data

        phantom_score_total = 0.0
        panel_score = 0.0

        if not (role_detail.phantomData and role_detail.phantomData.equipPhantomList):
            return {"panel": 0.0, "phantom": 0.0, "phantom_slot_scores": {}}

        calc = WuWaCalc(role_detail)
        calc.phantom_pre = calc.prepare_phantom()
        calc.phantom_card = calc.enhance_summation_phantom_value(calc.phantom_pre)
        calc.role_card = calc.enhance_summation_card_value(calc.phantom_card)
        calc.calc_temp = get_calc_map(
            calc.phantom_card,
            role_detail.role.roleName,
            role_detail.role.roleId,
            get_role_modal(role_detail),
        )

        _slot_scores = {}
        for idx, _ph in enumerate(role_detail.phantomData.equipPhantomList):
            if _ph and _ph.phantomProp:
                props = _ph.get_props()
                _s, _ = calc_phantom_score(role_detail.role.roleId, props, _ph.cost, calc.calc_temp)
                _s = min(_s, 50.0)
                phantom_score_total += _s
                _slot_scores[idx] = round(_s, 1)

        scoreDetail = ScoreDetailRegister.find_class(str(role_detail.role.roleId))
        if scoreDetail:
            score_calc_obj = scoreDetail[0] if isinstance(scoreDetail, list) else scoreDetail
            setattr(calc, "_score_title", score_calc_obj.get("title", ""))
            score_report = score_calc_obj["func"](calc, role_detail)
            if score_report is not None and hasattr(score_report, 'score'):
                panel_score = round(float(score_report.score), 2)

        return {"panel": panel_score, "phantom": round(phantom_score_total, 2), "phantom_slot_scores": _slot_scores}
    except Exception as _e:
        logger.warning(f"[鸣潮·面板diff] 评分计算失败: {_e}")
        return {"panel": 0.0, "phantom": 0.0, "phantom_slot_scores": {}}


# ── 数值解析 ──────────────────────────────────────────────────────────────────

def _parse_val(v):
    """'36.0%' → (36.0, '%'); '540' → (540, '')"""
    s = str(v).strip()
    if s in ("-", ""):
        return None, ""
    m = re.match(r"^([-\d.]+)\s*(%?)$", s)
    if m:
        return float(m.group(1)), m.group(2)
    return None, ""


# ── Diff 计算 ─────────────────────────────────────────────────────────────────

STAT_ORDER = ["生命", "攻击", "防御", "共鸣效率", "暴击", "暴击伤害",
              "属性伤害加成", "治疗效果加成", "普攻伤害加成", "重击伤害加成",
              "共鸣技能伤害加成", "共鸣解放伤害加成"]


def compute_stat_diff(old_char: Dict, new_char: Dict) -> List[Dict]:
    """比较 equipPhantomAddPropList, 返回变化的词条列表。"""
    old_props = {p["attributeName"]: p["attributeValue"] for p in old_char.get("equipPhantomAddPropList", [])}
    new_props = {p["attributeName"]: p["attributeValue"] for p in new_char.get("equipPhantomAddPropList", [])}

    # 固定顺序 + 追加不在固定列表中的
    ordered = [k for k in STAT_ORDER if k in old_props or k in new_props]
    ordered += [k for k in old_props if k not in set(ordered)]

    changes = []
    for key in ordered:
        old_v = old_props.get(key, "-")
        new_v = new_props.get(key, "-")
        on, os_ = _parse_val(old_v)
        nn, ns = _parse_val(new_v)
        if on is not None and nn is not None and os_ == ns:
            d = nn - on
            if abs(d) >= 0.05:
                sign = "+" if d > 0 else ""
                ds = f"{sign}{d:.1f}{os_}"
                changes.append({"name": key, "old": old_v, "new": new_v, "delta": d, "ds": ds, "up": d > 0})
        elif old_v != new_v:
            changes.append({"name": key, "old": old_v, "new": new_v, "delta": 0, "ds": "", "up": True})

    return changes


def _get_phantom_props(ph: Optional[Dict]) -> Dict[str, Tuple[str, bool]]:
    """返回 {属性名: (值, 是否主词条)}"""
    if not ph:
        return {}
    result = {}
    for p in ph.get("mainProps") or []:
        result[p["attributeName"]] = (p["attributeValue"], True)
    for p in ph.get("subProps") or []:
        if p["attributeName"] not in result:
            result[p["attributeName"]] = (p["attributeValue"], False)
    return result


def _score_to_phantom_grade(score: float) -> str:
    """单个声骸评分等级."""
    for thr, lbl in [(45, 'sss'), (40, 'ss'), (35, 's'), (30, 'a'), (24, 'b')]:
        if score >= thr:
            return lbl
    return 'c'


def get_phantom_total_grade(score: float) -> str:
    """声骸总评分等级: sss>=210, ss>=195, s>=175, a>=150, b>=120."""
    for thr, lbl in [(210, 'sss'), (195, 'ss'), (175, 's'), (150, 'a'), (120, 'b')]:
        if score >= thr:
            return lbl
    return 'c'


def _phantom_fingerprint(p: Optional[Dict]) -> str:
    """声骸游戏性指纹, 仅比较影响实战的字段."""
    if not p or not p.get("phantomProp"):
        return ""
    # ponytail: 用 json.dumps(sort_keys=True) 序列化 dict, 避免 sorted(dict) 报错
    props_key = lambda lst: str(sorted(
        (d.get("attributeName", ""), d.get("attributeValue", "")) for d in (lst or [])
    ))
    return "|".join([
        str(p["phantomProp"].get("phantomId", "")),
        str(p.get("level", "")),
        str(p.get("cost", "")),
        props_key(p.get("mainProps")),
        props_key(p.get("subProps")),
    ])


def _format_prop_delta(bv: str, av: str) -> Tuple[str, str]:
    """计算词条变化的 delta 字符串和 CSS class."""
    on, os_ = _parse_val(bv)
    nn, ns = _parse_val(av)
    d = nn - on if (on is not None and nn is not None and os_ == ns) else None
    cls = "up" if (d is not None and d > 0) else ("down" if (d is not None and d < 0) else "")
    if d is None:
        ds = ""
    elif os_ == "%":
        ds = f"({'+' if d > 0 else ''}{d:.1f}{os_})"
    else:
        ds = f"({'+' if d > 0 else ''}{int(d)})"
    return ds, cls


def compute_phantom_diff(old_char: Dict, new_char: Dict,
                         old_slot_scores: Optional[Dict] = None,
                         new_slot_scores: Optional[Dict] = None) -> List[Dict]:
    """按位置对比声骸, 返回有变化的声骸对列表 (含图标URL)."""
    old_list = old_char.get("phantomData", {}).get("equipPhantomList") or []
    new_list = new_char.get("phantomData", {}).get("equipPhantomList") or []
    old_slot_scores = old_slot_scores or {}
    new_slot_scores = new_slot_scores or {}

    pairs = []
    for i in range(max(len(old_list), len(new_list))):
        b = old_list[i] if i < len(old_list) else None
        a = new_list[i] if i < len(new_list) else None
        if not a and not b:
            continue
        if _phantom_fingerprint(b) == _phantom_fingerprint(a):
            continue

        ref = a if a else b
        cost = ref.get("cost", "?")
        old_name = (b or {}).get("phantomProp", {}).get("name", "(空)")
        new_name = (a or {}).get("phantomProp", {}).get("name", "(空)")

        bpp = _get_phantom_props(b)
        app = _get_phantom_props(a)

        diff_lines = []
        # 主词条变化
        for k in app:
            if k in bpp and bpp[k][1] and bpp[k][0] != app[k][0]:
                ds, cls = _format_prop_delta(bpp[k][0], app[k][0])
                diff_lines.append({"type": "changed_main", "icon": attr_icon_url(k), "name": k, "old": bpp[k][0], "new": app[k][0], "ds": ds, "cls": cls})
        # 删除的词条
        for k in bpp:
            if k not in app:
                diff_lines.append({"type": "removed", "icon": attr_icon_url(k), "name": k, "old": bpp[k][0]})
        # 新增的词条
        for k in app:
            if k not in bpp:
                diff_lines.append({"type": "added", "icon": attr_icon_url(k), "name": k, "new": app[k][0], "is_main": app[k][1]})
        # 副词条变化
        for k in app:
            if k in bpp and not bpp[k][1] and bpp[k][0] != app[k][0]:
                ds, cls = _format_prop_delta(bpp[k][0], app[k][0])
                diff_lines.append({"type": "changed_sub", "icon": attr_icon_url(k), "name": k, "old": bpp[k][0], "new": app[k][0], "ds": ds, "cls": cls})

        pairs.append({
            "slot": i,
            "cost": cost,
            "old_name": old_name,
            "new_name": new_name,
            "is_swap": old_name != new_name,
            "old_is_empty": not b or not b.get("phantomProp"),
            "old_level": b.get("level", "?") if b else "?",
            "new_level": a.get("level", "?") if a else "?",
            "old_score": old_slot_scores.get(i, 0.0),
            "new_score": new_slot_scores.get(i, 0.0),
            "old_grade_icon": score_icon_url(_score_to_phantom_grade(old_slot_scores.get(i, 0.0)), 48) if old_slot_scores.get(i, 0.0) > 0 else "",
            "new_grade_icon": score_icon_url(_score_to_phantom_grade(new_slot_scores.get(i, 0.0)), 48) if new_slot_scores.get(i, 0.0) > 0 else "",
            "old_icon": get_phantom_icon_url(b.get("phantomProp", {}) if b else {}),
            "new_icon": get_phantom_icon_url(a.get("phantomProp", {}) if a else {}),
            "lines": diff_lines,
        })

    return pairs


def compute_panel_diff(old_char: Dict, new_char: Dict,
                        old_slot_scores: Optional[Dict] = None,
                        new_slot_scores: Optional[Dict] = None) -> Dict:
    """计算完整面板 diff, 返回模板渲染用的 context。"""
    role = new_char.get("role", {})
    return {
        "char_name": role.get("roleName", "?"),
        "char_level": new_char.get("level", "?"),
        "char_id": str(role.get("roleId", "")),
        "element": role.get("attributeName", ""),
        "stat_changes": compute_stat_diff(old_char, new_char),
        "phantom_changes": compute_phantom_diff(old_char, new_char, old_slot_scores, new_slot_scores),
    }
