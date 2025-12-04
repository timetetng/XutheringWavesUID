import json
import random
import string
import time
from datetime import datetime, timedelta
import aiohttp
from aiohttp import TCPConnector

# 禁用安全警告
# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning) # aiohttp 不需要这个

# Mappings
POOL_TYPE_MAP = {
    "角色精准调谐": "1",
    "武器精准调谐": "2",
    "角色调谐（常驻池）": "3",
    "武器调谐（常驻池）": "4",
    "新手调谐": "5",
    "新手自选唤取": "6",
    "新手自选唤取（感恩定向唤取）": "7",
    "角色新旅唤取": "8",
    "武器新旅唤取": "9"
}

FILLER_ITEM = {
    "resourceId": 21040023,
    "qualityLevel": 3,
    "resourceType": "武器",
    "name": "源能臂铠·测肆",
    "count": 1
}

def generate_random_string(length, chars):
    return ''.join(random.choice(chars) for _ in range(length))

def generate_union_id(length=28):
    chars = string.ascii_letters + string.digits + "_"
    return generate_random_string(length, chars)

def generate_sign(length=32):
    chars = string.digits + "abcdef"
    return generate_random_string(length, chars)

def get_timestamp_minus_1s(time_str):
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        dt_new = dt - timedelta(seconds=1)
        return dt_new.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return time_str

async def fetch_sanyueqi_data(uid: str):
    url = "https://api3.sanyueqi.cn/api/v2/game_user/get_sr_draw_v3"
    current_time_ms = str(int(time.time() * 1000))
    random_union_id = generate_union_id()
    random_sign = generate_sign()

    params = {
        "uid": uid,
        "union_id": random_union_id
    }

    headers = {
        "Host": "api3.sanyueqi.cn",
        "Connection": "keep-alive",
        "time": current_time_ms,
        "sign": random_sign,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541411) XWEB/16965",
        "xweb_xhr": "1",
        "Content-Type": "application/json",
        "version": "100",
        "platform": "weixin",
        "Accept": "*/*",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://servicewechat.com/wx715e22143bcda767/36/page-frame.html",
        "Accept-Language": "zh-CN,zh;q=0.9"
    }

    try:
        async with aiohttp.ClientSession(connector=TCPConnector(ssl=False)) as session:
            async with session.get(url, params=params, headers=headers, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
    except Exception:
        pass
    return None

def merge_gacha_data(original_data: dict, latest_data: dict) -> dict:
    export_info = original_data.get('info', {})
    original_list = original_data.get('list', [])
    
    latest_5stars = []
    card_analysis = latest_data.get('data', {}).get('card_analysis_json', {})
    
    def extract_five_cards(d):
        if isinstance(d, dict):
            if 'five_cards' in d and isinstance(d['five_cards'], list):
                for card in d['five_cards']:
                     p_type = card.get('cardPoolType')
                     p_type_code = POOL_TYPE_MAP.get(p_type, p_type)
                     
                     # Safer field access
                     card_name = card.get('name', '未知五星')
                     card_time = card.get('time', '')
                     draw_total = card.get('draw_total', 1)
                     
                     # Skip invalid entries
                     if not card_time:
                         continue

                     latest_5stars.append({
                        "time": card_time,
                        "name": card_name,
                        "cardPoolType": p_type_code,
                        "draw_total": draw_total,
                        "resourceId": card.get('resourceId', card.get('item_id')),
                        "qualityLevel": 5,
                        "resourceType": card.get('resourceType', '角色'),
                        "is_latest": True
                     })
            for k, v in d.items():
                extract_five_cards(v)
        elif isinstance(d, list):
            for item in d:
                extract_five_cards(item)
                
    extract_five_cards(card_analysis)
    
    # Use .get() when creating the set to avoid KeyError if 'cardPoolType' is missing
    # Filter out None values
    orig_types = [str(x.get('cardPoolType')) for x in original_list if x.get('cardPoolType')]
    latest_types = [str(x.get('cardPoolType')) for x in latest_5stars if x.get('cardPoolType')]
    
    all_pools = set(orig_types + latest_types)
    
    merged_list = []
    
    for pool_id in sorted(list(all_pools)):
        # Sort logic
        O_all = sorted([x for x in original_list if str(x.get('cardPoolType')) == str(pool_id)], key=lambda x: x.get('time', ''))
        L_5s = sorted([x for x in latest_5stars if str(x.get('cardPoolType')) == str(pool_id)], key=lambda x: x.get('time', ''))
        
        O_5s = [x for x in O_all if x.get('qualityLevel') == 5]
        
        pool_merged_items = []
        
        if not O_5s:
            for cp in L_5s:
                filler_count = cp['draw_total'] - 1
                filler_time = get_timestamp_minus_1s(cp['time'])
                for _ in range(filler_count):
                    f = FILLER_ITEM.copy()
                    f['cardPoolType'] = str(pool_id)
                    f['time'] = filler_time
                    pool_merged_items.append(f)
                cp_item = {
                    "cardPoolType": str(pool_id),
                    "resourceId": cp['resourceId'],
                    "qualityLevel": 5,
                    "resourceType": cp['resourceType'],
                    "name": cp['name'],
                    "count": 1,
                    "time": cp['time']
                }
                pool_merged_items.append(cp_item)
            pool_merged_items.extend(O_all)
            
        else:
            x = O_5s[0]
            
            match_idx = None
            for i, cand in enumerate(L_5s):
                if cand['time'] == x['time'] and cand['name'] == x['name']:
                    is_match = True
                    for offset in range(1, 3):
                        if (i + offset < len(L_5s)) and (offset < len(O_5s)):
                            l_next = L_5s[i + offset]
                            o_next = O_5s[offset]
                            if l_next['time'] != o_next['time'] or l_next['name'] != o_next['name']:
                                is_match = False
                                break
                    if is_match:
                        match_idx = i
                        break
            
            if match_idx is None:
                for cp in L_5s:
                    filler_count = cp['draw_total'] - 1
                    filler_time = get_timestamp_minus_1s(cp['time'])
                    for _ in range(filler_count):
                        f = FILLER_ITEM.copy()
                        f['cardPoolType'] = str(pool_id)
                        f['time'] = filler_time
                        pool_merged_items.append(f)
                    cp_item = {
                        "cardPoolType": str(pool_id),
                        "resourceId": cp['resourceId'],
                        "qualityLevel": 5,
                        "resourceType": cp['resourceType'],
                        "name": cp['name'],
                        "count": 1,
                        "time": cp['time']
                    }
                    pool_merged_items.append(cp_item)
                pool_merged_items.extend(O_all)
            
            else:
                for i in range(match_idx):
                    cp = L_5s[i]
                    filler_count = cp['draw_total'] - 1
                    filler_time = get_timestamp_minus_1s(cp['time'])
                    for _ in range(filler_count):
                        f = FILLER_ITEM.copy()
                        f['cardPoolType'] = str(pool_id)
                        f['time'] = filler_time
                        pool_merged_items.append(f)
                    cp_item = {
                        "cardPoolType": str(pool_id),
                        "resourceId": cp['resourceId'],
                        "qualityLevel": 5,
                        "resourceType": cp['resourceType'],
                        "name": cp['name'],
                        "count": 1,
                        "time": cp['time']
                    }
                    pool_merged_items.append(cp_item)
                
                cp_x = L_5s[match_idx]
                
                items_before_x = []
                for item in O_all:
                    if item['time'] == x['time'] and item['name'] == x['name']:
                        break 
                    items_before_x.append(item)
                
                count_existing = len(items_before_x)
                target_count = cp_x['draw_total']
                
                diff = target_count - count_existing
                
                if diff > 0:
                    filler_time = get_timestamp_minus_1s(x['time'])
                    fillers = []
                    for _ in range(diff):
                        f = FILLER_ITEM.copy()
                        f['cardPoolType'] = str(pool_id)
                        f['time'] = filler_time
                        fillers.append(f)
                    pool_merged_items.extend(fillers)
                
                pool_merged_items.extend(O_all)

        merged_list.extend(pool_merged_items)

    merged_list.sort(key=lambda x: x.get('time', ''), reverse=True)
    
    return {
        "info": export_info,
        "list": merged_list
    }
