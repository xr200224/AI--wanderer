#!/usr/bin/env python3
"""
Local RapidAPI proxy for AI Wanderer.

Why this exists:
- RapidAPI keys must stay on the server side, not in index.html.
- The frontend calls /api/tripadvisor/search.
- This proxy calls TripAdvisor providers on RapidAPI and normalizes results.

Environment:
  RAPIDAPI_KEY                    required
  RAPIDAPI_TRIPADVISOR_HOST       default: tripadvisor-com1.p.rapidapi.com
  RAPIDAPI_TRIPADVISOR_BASE_PATH  optional, provider-specific
  PORT                            default: 8787
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from html import unescape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "").strip()
RAPIDAPI_HOST = os.environ.get(
    "RAPIDAPI_TRIPADVISOR_HOST",
    "tripadvisor-com1.p.rapidapi.com",
).strip()
BASE_PATH = os.environ.get("RAPIDAPI_TRIPADVISOR_BASE_PATH", "").rstrip("/")
TIMEOUT_SECONDS = float(os.environ.get("RAPIDAPI_TIMEOUT", "12"))


CITY_GEO_IDS = {
    "北京": "294212",
    "上海": "308272",
    "广州": "298555",
    "深圳": "297415",
    "成都": "297463",
    "重庆": "294213",
    "西安": "298557",
    "杭州": "298559",
    "南京": "294220",
    "苏州": "297442",
    "武汉": "297437",
    "长沙": "494932",
    "厦门": "297407",
    "青岛": "297458",
    "昆明": "298558",
    "大理": "303781",
    "丽江": "303783",
    "桂林": "298556",
    "三亚": "297427",
    "安康": "1152549",
    "New York": "60763",
    "纽约": "60763",
}

PLACE_QUERY_ALIASES = {
    "洪崖洞": ["hongya", "hongyadong"],
    "磁器口": ["ciqikou", "porcelain port"],
    "磁器口古镇": ["ciqikou", "porcelain port"],
    "解放碑": ["jiefangbei", "liberation monument"],
    "解放碑步行街": ["jiefangbei", "liberation monument"],
    "李子坝": ["liziba", "monorail"],
    "李子坝轻轨穿楼": ["liziba", "monorail"],
    "南山一棵树": ["nanshan", "one tree"],
    "黄桷坪": ["huangjueping", "graffiti street"],
    "黄桷坪涂鸦街": ["huangjueping", "graffiti street"],
    "涂鸦街": ["huangjueping", "graffiti street"],
    "鹅岭二厂": ["eling", "second factory", "testbed 2"],
    "鹅岭二厂文创公园": ["eling", "second factory", "testbed 2"],
    "北仓": ["beicang"],
    "北仓文创街区": ["beicang"],
    "山城步道": ["shancheng", "mountain city", "mountain city trail"],
    "十八梯": ["shibati"],
    "十八梯传统风貌区": ["shibati"],
    "较场口": ["jiaochangkou"],
    "较场口夜市": ["jiaochangkou"],
    "武隆": ["wulong", "karst"],
    "武隆天坑": ["wulong", "karst"],
    "兵马俑": ["terra-cotta", "terracotta", "warriors"],
}


BROAD_SEARCH_RE = re.compile(
    r"推荐|景点|打卡|榜|排行|热门|经典|必去|好玩|攻略|路线|行程|酒店|住宿|美食|餐厅|小吃|商圈|周边"
)
BAD_SEARCH_RE = re.compile(r"百科|wikipedia|日历|节日|宣传月|别称|factorial|motel\s*6", re.I)
DESTINATION_ALIASES = {
    "伊犁": ["伊犁", "ili", "yili", "xinjiang"],
    "青海湖": ["青海湖", "qinghai lake", "qinghai"],
    "大理": ["大理", "dali", "yunnan"],
    "桂林": ["桂林", "guilin"],
    "张家界": ["张家界", "zhangjiajie"],
    "青岛": ["青岛", "qingdao"],
    "贵阳": ["贵阳", "guiyang", "guizhou"],
    "西安": ["西安", "xi'an", "xian", "xi’an"],
    "三亚": ["三亚", "sanya", "hainan"],
    "昆明": ["昆明", "kunming", "yunnan"],
    "哈尔滨": ["哈尔滨", "harbin"],
    "厦门": ["厦门", "xiamen"],
    "成都": ["成都", "chengdu"],
    "杭州": ["杭州", "hangzhou"],
    "苏州": ["苏州", "suzhou"],
    "南京": ["南京", "nanjing"],
    "北京": ["北京", "beijing"],
    "敦煌": ["敦煌", "dunhuang"],
    "洛阳": ["洛阳", "luoyang"],
}

SEASONAL_DESTINATION_CANDIDATES = {
    1: [
        {"city": "三亚", "title": "海岛暖冬与亲海度假", "season": "暖冬避寒"},
        {"city": "昆明", "title": "春城花市与滇池海鸥", "season": "温暖慢游"},
        {"city": "哈尔滨", "title": "冰雪大世界与俄式街区", "season": "冰雪季"},
        {"city": "厦门", "title": "海边散步与南洋街巷", "season": "温和海滨"},
        {"city": "西双版纳", "title": "热带雨林与傣味年节", "season": "热带风情"},
    ],
    2: [
        {"city": "三亚", "title": "海岛阳光与避寒假期", "season": "避寒"},
        {"city": "大理", "title": "洱海暖阳与古城慢游", "season": "暖阳"},
        {"city": "厦门", "title": "海岸骑行与老城咖啡", "season": "海滨"},
        {"city": "哈尔滨", "title": "冰雪收官与冬日城市", "season": "冰雪"},
        {"city": "广州", "title": "花城年味与早茶美食", "season": "岭南年味"},
    ],
    3: [
        {"city": "武汉", "title": "樱花季与江城漫游", "season": "赏花"},
        {"city": "杭州", "title": "西湖春色与茶山新绿", "season": "踏青"},
        {"city": "婺源", "title": "油菜花海与徽派村落", "season": "花海"},
        {"city": "南京", "title": "城墙梧桐与秦淮春游", "season": "春游"},
        {"city": "大理", "title": "苍山洱海与春日慢游", "season": "温暖"},
    ],
    4: [
        {"city": "洛阳", "title": "牡丹花会与古都夜游", "season": "花会"},
        {"city": "杭州", "title": "西湖春水与龙井茶香", "season": "春茶"},
        {"city": "苏州", "title": "园林春景与江南水巷", "season": "江南"},
        {"city": "桂林", "title": "漓江烟雨与山水初夏", "season": "山水"},
        {"city": "西安", "title": "古城花事与博物馆深游", "season": "错峰"},
    ],
    5: [
        {"city": "伊犁", "title": "草原花海与雪山公路", "season": "草原花季"},
        {"city": "大理", "title": "洱海风与苍山初夏", "season": "避暑"},
        {"city": "张家界", "title": "峰林云海与森林氧吧", "season": "山地"},
        {"city": "青岛", "title": "海风街区与德式建筑", "season": "海滨"},
        {"city": "成都", "title": "川西门户与市井美食", "season": "轻松"},
    ],
    6: [
        {"city": "伊犁", "title": "草原花海与雪山公路", "season": "草原花季"},
        {"city": "青海湖", "title": "湖畔花田与高原清凉", "season": "高原避暑"},
        {"city": "大理", "title": "洱海风与苍山避暑", "season": "清凉慢游"},
        {"city": "桂林", "title": "漓江丰水期与喀斯特山水", "season": "山水丰水期"},
        {"city": "张家界", "title": "峰林云海与森林氧吧", "season": "山地避暑"},
        {"city": "青岛", "title": "海滨街区与初夏海风", "season": "海滨避暑"},
        {"city": "贵阳", "title": "凉爽城市与黔中山水", "season": "避暑"},
        {"city": "西安", "title": "古都错峰与夜游博物馆", "season": "错峰文化游"},
    ],
    7: [
        {"city": "青海湖", "title": "油菜花海与高原湖泊", "season": "避暑花季"},
        {"city": "贵阳", "title": "清凉山城与瀑布峡谷", "season": "避暑"},
        {"city": "伊犁", "title": "草原深绿与独库公路", "season": "草原"},
        {"city": "大理", "title": "洱海风与苍山雨后", "season": "避暑"},
        {"city": "青岛", "title": "海滨度假与啤酒季", "season": "海滨"},
    ],
    8: [
        {"city": "贵阳", "title": "清凉避暑与瀑布峡谷", "season": "避暑"},
        {"city": "青海湖", "title": "高原湖泊与草原花海", "season": "高原"},
        {"city": "大理", "title": "苍山洱海与慢生活", "season": "避暑"},
        {"city": "长白山", "title": "森林天池与火山地貌", "season": "山地"},
        {"city": "青岛", "title": "海风沙滩与城市漫步", "season": "海滨"},
    ],
    9: [
        {"city": "喀纳斯", "title": "秋色湖湾与北疆森林", "season": "秋色"},
        {"city": "敦煌", "title": "大漠晴空与丝路遗产", "season": "西北"},
        {"city": "北京", "title": "秋高气爽与古建公园", "season": "秋游"},
        {"city": "南京", "title": "梧桐街巷与民国建筑", "season": "城市漫游"},
        {"city": "桂林", "title": "山水秋光与漓江游船", "season": "山水"},
    ],
    10: [
        {"city": "北京", "title": "红叶古建与秋日公园", "season": "金秋"},
        {"city": "喀纳斯", "title": "北疆秋色与森林湖泊", "season": "秋色"},
        {"city": "腾冲", "title": "银杏村与火山温泉", "season": "银杏"},
        {"city": "南京", "title": "梧桐大道与秦淮夜色", "season": "秋游"},
        {"city": "西安", "title": "古都秋色与博物馆深游", "season": "文化游"},
    ],
    11: [
        {"city": "腾冲", "title": "银杏村与温泉慢游", "season": "银杏"},
        {"city": "厦门", "title": "海滨暖阳与街区漫游", "season": "暖冬"},
        {"city": "广州", "title": "花城秋冬与早茶美食", "season": "美食"},
        {"city": "昆明", "title": "春城花事与滇池海鸥", "season": "暖阳"},
        {"city": "南京", "title": "梧桐落叶与城市秋色", "season": "秋色"},
    ],
    12: [
        {"city": "哈尔滨", "title": "冰雪城市与冬日童话", "season": "冰雪"},
        {"city": "三亚", "title": "海岛暖阳与避寒度假", "season": "避寒"},
        {"city": "昆明", "title": "春城暖冬与滇池海鸥", "season": "暖阳"},
        {"city": "厦门", "title": "海边街巷与温和假期", "season": "海滨"},
        {"city": "广州", "title": "暖冬花城与岭南美食", "season": "美食"},
    ],
}


def deep_values(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from deep_values(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from deep_values(item)


def first_value(obj: dict, keys: list[str], default: Any = "") -> Any:
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
    for node in deep_values(obj):
        if node is obj:
            continue
        for key in keys:
            if key in node and node[key] not in (None, ""):
                return node[key]
    return default


def unwrap_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("string", "text", "htmlString", "localizedString", "rating", "label", "title", "name"):
            text = unwrap_text(value.get(key))
            if text:
                return text
    return ""


def clean_html(value: Any) -> str:
    text = unwrap_text(value)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_image(obj: dict) -> str:
    sizes = obj.get("sizes")
    if isinstance(sizes, dict):
        template = unwrap_text(sizes.get("urlTemplate"))
        if template:
            return template.replace("{width}", "640").replace("{height}", "480")
    template = unwrap_text(obj.get("urlTemplate"))
    if template:
        return template.replace("{width}", "640").replace("{height}", "480")

    keys = [
        "image",
        "photo",
        "photoUrl",
        "photo_url",
        "thumbnail",
        "thumbnailUrl",
        "thumbnail_url",
        "primaryPhoto",
        "cardPhoto",
        "cardPhotos",
    ]
    found = first_value(obj, keys, "")
    if isinstance(found, str):
        return found
    if isinstance(found, list) and found:
        return extract_image(found[0]) if isinstance(found[0], dict) else str(found[0])
    if isinstance(found, dict):
        sizes = found.get("sizes")
        if isinstance(sizes, dict):
            template = unwrap_text(sizes.get("urlTemplate"))
            if template:
                return template.replace("{width}", "640").replace("{height}", "480")
        template = unwrap_text(found.get("urlTemplate"))
        if template:
            return template.replace("{width}", "640").replace("{height}", "480")
        return unwrap_text(first_value(found, ["url", "source", "link"], ""))
    return ""


def extract_images(obj: Any, limit: int = 6) -> list[str]:
    urls: list[str] = []
    for node in deep_values(obj):
        if not isinstance(node, dict):
            continue
        url = extract_image(node)
        if url and url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def extract_content_id(item: dict) -> str:
    save_id = item.get("saveId")
    if isinstance(save_id, dict):
        sid = unwrap_text(save_id.get("id"))
        if sid:
            return sid
    card_link = item.get("cardLink")
    if isinstance(card_link, dict):
        params = first_value(card_link, ["params"], {})
        if isinstance(params, dict):
            cid = unwrap_text(params.get("contentId") or params.get("detailId"))
            if cid:
                return cid
        route_url = unwrap_text(first_value(card_link, ["url", "nonCanonicalUrl"], ""))
        match = re.search(r"(?:contentId=|[-_]?d)(\d{4,})", route_url)
        if match:
            return match.group(1)
    return unwrap_text(first_value(item, ["locationId", "location_id", "geoId", "id", "place_id"], ""))


def extract_content_type(item: dict, fallback: str = "") -> str:
    card_link = item.get("cardLink")
    if isinstance(card_link, dict):
        params = first_value(card_link, ["params"], {})
        if isinstance(params, dict):
            ctype = unwrap_text(params.get("contentType"))
            if ctype:
                return ctype
    save_id = item.get("saveId")
    if isinstance(save_id, dict):
        ctype = unwrap_text(save_id.get("type"))
        if ctype and ctype != "location":
            return ctype
    return fallback


def normalize_item(item: dict, city: str, index: int) -> dict:
    name = unwrap_text(first_value(item, ["name", "title", "localizedName", "label", "cardTitle"], ""))
    place_id = extract_content_id(item)
    content_type = extract_content_type(item)
    rating = unwrap_text(first_value(item, ["rating", "bubbleRating", "reviewRating", "localizedRating"], ""))
    reviews = unwrap_text(first_value(item, ["numReviews", "num_reviews", "reviewCount", "reviewsCount", "numberReviews"], ""))
    address = unwrap_text(first_value(item, ["address", "addressString", "locationString", "location_string", "primaryInfo", "secondaryInfo"], ""))
    ranking = unwrap_text(first_value(item, ["rankingString", "ranking", "rankingText", "trackingTitle"], ""))
    category = unwrap_text(first_value(item, ["category", "subcategory", "type", "primaryInfo"], ""))
    link = unwrap_text(first_value(item, ["webUrl", "website", "url", "externalUrl", "link"], ""))
    image = extract_image(item)
    images = extract_images(item, 6)
    price = clean_html(first_value(item, ["priceForDisplay", "merchandisingText", "priceWithPrefix"], ""))
    latitude = unwrap_text(first_value(item, ["latitude", "lat"], ""))
    longitude = unwrap_text(first_value(item, ["longitude", "lng", "lon"], ""))

    if not name:
        name = f"{city}热门地点 {index + 1}"

    return {
        "id": str(place_id or f"tripadvisor_{index + 1}"),
        "content_id": str(place_id or ""),
        "content_type": str(content_type or ""),
        "name": str(name),
        "rating": str(rating or ""),
        "review_count": str(reviews or ""),
        "address": str(address or f"{city} · {name}"),
        "ranking": str(ranking or ""),
        "category": str(category or ""),
        "url": str(link or ""),
        "image_url": image,
        "images": images,
        "price": price,
        "latitude": latitude,
        "longitude": longitude,
        "raw": item,
    }


def get_city_geo_id(city: str) -> str:
    if city in CITY_GEO_IDS:
        return CITY_GEO_IDS[city]
    city_key = city.replace("市", "").strip()
    return CITY_GEO_IDS.get(city_key, "")


def pick_records(payload: Any, limit: int) -> list[dict]:
    records: list[dict] = []
    for node in deep_values(payload):
        if not isinstance(node, dict):
            continue
        name = unwrap_text(first_value(node, ["name", "title", "localizedName", "label", "cardTitle"], ""))
        location_id = unwrap_text(first_value(node, ["locationId", "location_id", "geoId", "id", "saveId", "trackingTitle"], ""))
        if name and location_id:
            records.append(node)
        if len(records) >= limit:
            break
    return records


def pick_category_records(payload: Any, kind: str, limit: int) -> list[dict]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        preferred_key = {
            "hotels": "hotels",
            "restaurants": "restaurants",
            "attractions": "attractions",
        }.get(kind)
        if preferred_key and isinstance(data.get(preferred_key), list):
            return [item for item in data[preferred_key] if isinstance(item, dict)][:limit]
    return pick_records(payload, limit)


def query_aliases(query: str) -> list[str]:
    q = str(query or "").strip().lower()
    aliases = [q] if q else []
    for key, values in PLACE_QUERY_ALIASES.items():
        if key in str(query or ""):
            aliases.extend(values)
    return [a for a in dict.fromkeys(aliases) if a]


def record_search_text(item: dict) -> str:
    parts = [
        unwrap_text(first_value(item, ["name", "title", "localizedName", "label", "cardTitle"], "")),
        unwrap_text(first_value(item, ["primaryInfo", "secondaryInfo", "rankingString", "ranking", "trackingTitle"], "")),
    ]
    return " ".join(parts).lower()


def is_specific_place_query(query: str) -> bool:
    q = str(query or "").strip()
    if not re.search(r"[\u4e00-\u9fff]", q):
        return False
    if BROAD_SEARCH_RE.search(q):
        return False
    return len(q) >= 2


def rank_records_for_query(records: list[dict], query: str) -> list[dict]:
    aliases = query_aliases(query)
    if not aliases:
        return records

    def score(item: dict) -> int:
        text = record_search_text(item)
        value = 0
        for alias in aliases:
            if alias and alias in text:
                value += 20 + min(len(alias), 12)
        title = unwrap_text(first_value(item, ["cardTitle", "name", "title"], "")).lower()
        if aliases and title.startswith(("1. ", "2. ", "3. ")):
            title = re.sub(r"^\d+\.\s*", "", title)
        for alias in aliases:
            if alias and title.startswith(alias):
                value += 30
        return value

    ranked = sorted(records, key=score, reverse=True)
    if not ranked:
        return []
    if score(ranked[0]) > 0:
        return ranked
    return [] if len(aliases) > 1 or is_specific_place_query(query) else records


def rapidapi_get(path: str, params: dict[str, Any]) -> Any:
    if not RAPIDAPI_KEY:
        raise RuntimeError("Missing RAPIDAPI_KEY environment variable")

    query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    url = f"https://{RAPIDAPI_HOST}{path}"
    if query:
        url += f"?{query}"

    req = urllib.request.Request(
        url,
        headers={
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": RAPIDAPI_HOST,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"RapidAPI {exc.code}: {body[:800]}") from exc
    with resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def http_get_text(url: str, timeout: float = 8) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(240_000)
    return raw.decode("utf-8", errors="ignore")


def strip_tags(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value or "", flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", unescape(value)).strip()


def decode_duckduckgo_url(url: str) -> str:
    url = unescape(url or "")
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    target = (query.get("uddg") or [""])[0]
    return target or url


def web_search_snippets(query: str, limit: int = 8) -> list[dict[str, str]]:
    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    html = http_get_text(url)
    results: list[dict[str, str]] = []
    blocks = re.findall(r'<div class="result(?: results_links_deep)?[^"]*".*?</div>\s*</div>', html, flags=re.S)
    if not blocks:
        blocks = re.findall(r'<a rel="nofollow" class="result__a".*?</a>.*?(?:<a|$)', html, flags=re.S)
    for block in blocks:
        link_match = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.S)
        if not link_match:
            continue
        snippet_match = re.search(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', block, flags=re.S)
        href = decode_duckduckgo_url(link_match.group(1))
        title = strip_tags(link_match.group(2))
        snippet = strip_tags(snippet_match.group(1) if snippet_match else "")
        if title and not BAD_SEARCH_RE.search(title):
            results.append({"title": title, "snippet": snippet, "url": href})
        if len(results) >= limit:
            break
    if results:
        return results

    bing_url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "mkt": "zh-CN", "setlang": "zh-CN"})
    bing_html = http_get_text(bing_url)
    for block in re.findall(r'<li class="b_algo"[^>]*>.*?</li>', bing_html, flags=re.S):
        link_match = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>', block, flags=re.S)
        if not link_match:
            continue
        snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, flags=re.S)
        title = strip_tags(link_match.group(2))
        snippet = strip_tags(snippet_match.group(1) if snippet_match else "")
        if title and not BAD_SEARCH_RE.search(title):
            results.append({"title": title, "snippet": snippet, "url": unescape(link_match.group(1))})
        if len(results) >= limit:
            break
    return results


def month_focus(month: int) -> str:
    return {
        1: "避寒、冰雪、年味",
        2: "避寒、春节错峰、暖阳",
        3: "赏花、踏青、春游",
        4: "花季、江南、山水",
        5: "初夏、草原、海滨",
        6: "避暑、草原花海、高原湖泊、山水丰水期",
        7: "避暑、高原、海滨、草原",
        8: "避暑、亲水、高原、山地",
        9: "秋色、西北、错峰",
        10: "金秋、红叶、古都",
        11: "银杏、暖冬、美食",
        12: "冰雪、避寒、暖冬",
    }.get(month, "当季舒适度、景观窗口、热门口碑")


def chinese_month(month: int) -> str:
    names = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]
    if 1 <= month <= 12:
        return names[month - 1] + "月"
    return f"{month}月"


def english_month(month: int) -> str:
    names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    if 1 <= month <= 12:
        return names[month - 1]
    return str(month)


def direct_travel_source_urls(month: int) -> list[str]:
    name = english_month(month).lower()
    urls = [
        f"https://www.topchinatravel.com/china-guide/best-places-to-visit-in-china-in-{name}.htm",
        f"https://quietroutes.com/travel-guide/best-places-to-travel-in-china-in-{name}/",
        f"https://cdebtrip.com/travel-guide/best-places-to-travel-in-china-in-{name}/",
    ]
    if month == 6:
        urls.extend([
            "https://www.chinadragontravel.com/six-chinas-best-travel-destinations-in-june/",
            "https://gochina.cc/top-7-places-to-visit-in-june-in-china/",
        ])
    return urls


def fetch_travel_source(url: str) -> dict[str, str] | None:
    html = http_get_text(url, timeout=3.5)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.S | re.I)
    title = strip_tags(title_match.group(1) if title_match else url)
    body_text = strip_tags(re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I))
    if not body_text:
        return None
    return {
        "title": title,
        "snippet": body_text[:1600],
        "url": url,
    }


def destination_discover(month: int, origin: str, limit: int) -> dict:
    month = month if 1 <= month <= 12 else date.today().month
    candidates = [dict(item) for item in SEASONAL_DESTINATION_CANDIDATES.get(month, [])]
    if not candidates:
        candidates = [dict(item) for item in SEASONAL_DESTINATION_CANDIDATES[date.today().month]]

    query = f"{chinese_month(month)} 国内最适合旅游的目的地 推荐 避暑 花季 错峰 攻略"
    if origin:
        query += f" 从{origin}出发"

    search_results: list[dict[str, str]] = []
    search_error = ""
    for source_url in direct_travel_source_urls(month):
        try:
            source = fetch_travel_source(source_url)
            if source:
                search_results.append(source)
        except Exception:
            pass

    errors: list[str] = []
    if len(search_results) < 2:
        search_queries = [
            query,
            f"best places to travel in China in {english_month(month)}",
            f"China {english_month(month)} travel destinations summer cool weather",
        ]
        seen_urls: set[str] = {item.get("url", "") for item in search_results}
        for search_query in search_queries:
            try:
                for result in web_search_snippets(search_query, 8):
                    url = result.get("url", "")
                    if url and url in seen_urls:
                        continue
                    seen_urls.add(url)
                    search_results.append(result)
                    if len(search_results) >= 10:
                        break
            except Exception as exc:
                errors.append(str(exc))
            if len(search_results) >= 10:
                break
    search_error = "; ".join(errors)

    haystack = "\n".join(f"{r.get('title','')} {r.get('snippet','')}" for r in search_results).lower()
    month_words = month_focus(month)

    scored: list[dict[str, Any]] = []
    for index, item in enumerate(candidates):
        city = item["city"]
        variants = set(DESTINATION_ALIASES.get(city, [city, city.replace("市", "")]))
        web_hits = sum(1 for value in variants if value and value.lower() in haystack)
        source = next(
            (r for r in search_results if any(v and v.lower() in f"{r.get('title','')} {r.get('snippet','')}".lower() for v in variants)),
            search_results[0] if search_results else {},
        )
        score = 62 + max(0, 10 - index) + web_hits * 9
        scored.append({**item, "score": score, "source": source})

    scored.sort(key=lambda x: x["score"], reverse=True)
    selected = scored[: max(limit, 4)]

    enriched: list[dict[str, Any]] = []
    for item in selected:
        city = item["city"]
        score = float(item["score"])
        image = f"https://loremflickr.com/800/560/{urllib.parse.quote(city)},travel,landmark/all?lock={abs(hash(city + str(month))) % 997}"

        source = item.get("source") or {}
        enriched.append({
            "city": city,
            "title": item["title"],
            "season": item["season"],
            "month": month,
            "score": round(score, 1),
            "reason": f"{month}月重点看{month_words}；{item['season']}窗口期更匹配。",
            "fit": "当季首选" if score >= 82 else "备选推荐",
            "rating": "",
            "review_count": "",
            "top_poi": "",
            "image_url": image,
            "source_title": source.get("title", ""),
            "source_url": source.get("url", ""),
            "tripadvisor_error": "",
        })

    enriched.sort(key=lambda x: x["score"], reverse=True)
    return {
        "ok": True,
        "month": month,
        "origin": origin,
        "focus": month_words,
        "query": query,
        "search_source": "duckduckgo-html",
        "search_error": search_error,
        "search_results": search_results[:5],
        "items": enriched[:limit],
        "fetched_at": int(time.time()),
    }


def category_to_path(category: str) -> str:
    if category in ("hotel", "hotels"):
        return "hotels"
    if category in ("restaurant", "restaurants", "food"):
        return "restaurants"
    return "attractions"


def category_search_name(kind: str) -> str:
    return {
        "hotels": "searchHotels",
        "restaurants": "searchRestaurants",
        "attractions": "searchAttractions",
    }.get(kind, "searchAttractions")


def tripadvisor_com1_path(kind: str) -> str:
    return {
        "hotels": "/hotels/search",
        "restaurants": "/restaurants/search",
        "attractions": "/attractions/search",
    }.get(kind, "/attractions/search")


def tripadvisor_com1_reviews_path(kind: str) -> str:
    return {
        "hotels": "/hotels/reviews",
        "restaurants": "/restaurants/reviews",
        "attractions": "/attractions/reviews",
    }.get(kind, "/attractions/reviews")


def tripadvisor_com1_media_path(kind: str) -> str:
    return {
        "hotels": "/hotels/media-gallery",
        "restaurants": "/restaurants/media-gallery",
        "attractions": "/attractions/media-gallery",
    }.get(kind, "/attractions/media-gallery")


def future_dates() -> tuple[str, str]:
    start = date.today() + timedelta(days=30)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def tripadvisor_com1_search(city: str, keyword: str, category: str, limit: int) -> dict:
    kind = category_to_path(category)
    geo_id = get_city_geo_id(city)
    if not geo_id:
        raise RuntimeError(f"暂未配置 {city} 的 TripAdvisor geoId")

    params: dict[str, Any] = {"geoId": geo_id}
    if keyword:
        params["query"] = keyword
    start, end = future_dates()
    if kind == "hotels":
        params.update({"checkIn": start, "checkOut": end})
    elif kind == "attractions":
        params.update({"startDate": start, "endDate": end})
    payload = rapidapi_get(tripadvisor_com1_path(kind), params)
    records = rank_records_for_query(pick_category_records(payload, kind, max(limit * 6, 30)), keyword)[:limit]
    normalized = [normalize_item(item, city, i) for i, item in enumerate(records[:limit])]
    return {
        "ok": True,
        "source": "rapidapi-tripadvisor-com1",
        "provider_host": RAPIDAPI_HOST,
        "category": kind,
        "query": " ".join(x for x in [city, keyword] if x).strip() or city,
        "geo_id": geo_id,
        "items": normalized,
        "fetched_at": int(time.time()),
    }


def find_tripadvisor_content(city: str, name: str, category: str = "attractions") -> dict:
    kind = category_to_path(category)
    geo_id = get_city_geo_id(city)
    if not geo_id:
        raise RuntimeError(f"暂未配置 {city} 的 TripAdvisor geoId")
    params: dict[str, Any] = {"geoId": geo_id}
    if name:
        params["query"] = name
    start, end = future_dates()
    if kind == "hotels":
        params.update({"checkIn": start, "checkOut": end})
    elif kind == "attractions":
        params.update({"startDate": start, "endDate": end})
    payload = rapidapi_get(tripadvisor_com1_path(kind), params)
    records = pick_category_records(payload, kind, 8)
    if not records:
        raise RuntimeError(f"TripAdvisor 未找到 {city} {name}")
    return normalize_item(records[0], city, 0)


def normalize_review(item: dict, index: int) -> dict:
    title = clean_html(item.get("htmlTitle") or item.get("title"))
    text = clean_html(item.get("htmlText") or item.get("text") or item.get("body"))
    user_profile = item.get("userProfile") if isinstance(item.get("userProfile"), dict) else {}
    user = clean_html(first_value(user_profile or {}, ["displayName", "username", "name"], "")) or f"TripAdvisor 用户 {index + 1}"
    rating = unwrap_text(first_value(item, ["rating", "bubbleRating", "localizedRating"], ""))
    date_text = clean_html(item.get("publishedDate") or item.get("dateVisitedValue"))
    visit_type = clean_html(item.get("tripTypeText") or item.get("tripTypeValue"))
    helpful = clean_html(first_value(item, ["helpfulVotes", "helpfulVoteText"], ""))
    photos = extract_images(item.get("photos") or [], 6)
    return {
        "id": unwrap_text(first_value(item, ["objectId", "stableDiffingType", "trackingTitle"], "")) or f"review_{index + 1}",
        "title": title,
        "text": text,
        "user": user,
        "rating": rating,
        "date": date_text,
        "visit_type": visit_type,
        "helpful": helpful,
        "photos": photos,
        "has_photos": bool(photos),
    }


def normalize_reviews(payload: Any, limit: int) -> tuple[list[dict], dict]:
    reviews: list[dict] = []
    summary: dict = {}
    for node in deep_values(payload):
        if not isinstance(node, dict):
            continue
        typename = unwrap_text(node.get("__typename"))
        if typename == "AppPresentation_TravelerInsights":
            summary = {
                "rating": unwrap_text(node.get("localizedRating") or node.get("rating")),
                "count": unwrap_text(node.get("count")),
                "rating_text": clean_html(node.get("ratingText")),
            }
        if typename == "AppPresentation_UserReviewSection":
            normalized = normalize_review(node, len(reviews))
            if normalized["text"] or normalized["title"]:
                reviews.append(normalized)
    reviews.sort(key=lambda r: (not r.get("has_photos"), -float(r.get("rating") or 0)))
    return reviews[:limit], summary


def normalize_media(payload: Any, limit: int = 12) -> list[dict]:
    media: list[dict] = []
    for node in deep_values(payload):
        if not isinstance(node, dict):
            continue
        typename = unwrap_text(node.get("__typename"))
        if typename not in ("Media_PhotoResult", "AppPresentation_MediaPageItemPhoto", "AppPresentation_Media"):
            continue
        url = extract_image(node)
        if not url:
            continue
        caption = clean_html(first_value(node, ["caption", "attribution"], ""))
        if not any(m["url"] == url for m in media):
            media.append({"url": url, "caption": caption})
        if len(media) >= limit:
            break
    if len(media) < limit:
        for url in extract_images(payload, limit):
            if not any(m["url"] == url for m in media):
                media.append({"url": url, "caption": ""})
            if len(media) >= limit:
                break
    return media


def tripadvisor_reviews(city: str, name: str, category: str, content_id: str, limit: int) -> dict:
    kind = category_to_path(category)
    matched: dict = {}
    if not content_id:
        matched = find_tripadvisor_content(city, name, kind)
        content_id = matched.get("content_id") or matched.get("id") or ""
        if matched.get("content_type"):
            kind = category_to_path(matched["content_type"])
    if not content_id:
        raise RuntimeError("Missing TripAdvisor contentId")
    review_payload = rapidapi_get(tripadvisor_com1_reviews_path(kind), {"contentId": content_id})
    reviews, summary = normalize_reviews(review_payload, limit)
    media: list[dict] = []
    try:
        media = normalize_media(rapidapi_get(tripadvisor_com1_media_path(kind), {"contentId": content_id}), 12)
    except Exception:
        media = []
    return {
        "ok": True,
        "source": "rapidapi-tripadvisor-com1",
        "provider_host": RAPIDAPI_HOST,
        "category": kind,
        "city": city,
        "query_name": name,
        "content_id": content_id,
        "matched": matched,
        "summary": summary,
        "reviews": reviews,
        "media": media,
        "fetched_at": int(time.time()),
    }


def tripadvisor_hotels(city: str, limit: int) -> dict:
    return tripadvisor_com1_search(city, "酒店", "hotels", limit)


def tripadvisor_destination(city: str, limit: int) -> dict:
    errors: dict[str, str] = {}

    def safe_items(label: str, keyword: str, category: str, item_limit: int) -> list[dict]:
        try:
            return tripadvisor_com1_search(city, keyword, category, item_limit).get("items", [])
        except Exception as exc:
            errors[label] = str(exc)
            return []

    attractions = safe_items("attractions", "景点", "attractions", limit)
    restaurants = safe_items("restaurants", "美食", "restaurants", min(limit, 4))
    hotels = safe_items("hotels", "酒店", "hotels", min(limit, 4))
    guide_cards = []
    for group, label in ((attractions, "热门景点"), (restaurants, "美食口碑"), (hotels, "住宿推荐")):
        for item in group[:3]:
            guide_cards.append({
                "type": label,
                "name": item.get("name"),
                "rating": item.get("rating"),
                "review_count": item.get("review_count"),
                "image_url": item.get("image_url"),
                "content_id": item.get("content_id"),
                "content_type": item.get("content_type"),
                "summary": item.get("category") or item.get("ranking") or item.get("address"),
            })
    return {
        "ok": True,
        "source": "rapidapi-tripadvisor-com1",
        "provider_host": RAPIDAPI_HOST,
        "city": city,
        "geo_id": get_city_geo_id(city),
        "attractions": attractions,
        "restaurants": restaurants,
        "hotels": hotels,
        "guide_cards": guide_cards,
        "errors": errors,
        "fetched_at": int(time.time()),
    }


def tripadvisor_search(city: str, keyword: str, category: str, limit: int) -> dict:
    if RAPIDAPI_HOST == "tripadvisor-com1.p.rapidapi.com":
        return tripadvisor_com1_search(city, keyword, category, limit)

    kind = category_to_path(category)
    query = " ".join(x for x in [city, keyword] if x).strip() or city

    location_payload = rapidapi_get(f"{BASE_PATH}/{kind}/searchLocation", {"query": city})
    location_records = pick_records(location_payload, 8)
    location_id = ""
    for record in location_records:
        location_id = str(first_value(record, ["locationId", "location_id", "geoId", "id"], ""))
        if location_id:
            break

    records: list[dict] = []
    detail_error = ""
    if location_id:
        endpoint = f"{BASE_PATH}/{kind}/{category_search_name(kind)}"
        candidates = [
            {"locationId": location_id, "query": keyword},
            {"geoId": location_id, "query": keyword},
            {"id": location_id, "query": keyword},
            {"locationId": location_id},
            {"geoId": location_id},
        ]
        for params in candidates:
            try:
                payload = rapidapi_get(endpoint, params)
                records = pick_records(payload, limit)
                if records:
                    break
            except Exception as exc:  # Provider parameter names differ across RapidAPI products.
                detail_error = str(exc)

    if not records:
        records = pick_records(location_payload, limit)

    normalized = [normalize_item(item, city, i) for i, item in enumerate(records[:limit])]
    return {
        "ok": True,
        "source": "rapidapi-tripadvisor",
        "provider_host": RAPIDAPI_HOST,
        "category": kind,
        "query": query,
        "location_id": location_id,
        "detail_error": detail_error,
        "items": normalized,
        "fetched_at": int(time.time()),
    }


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def send_json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/tripadvisor/health":
            self.send_json(200, {
                "ok": True,
                "rapidapi_key_configured": bool(RAPIDAPI_KEY),
                "provider_host": RAPIDAPI_HOST,
            })
            return

        if parsed.path == "/api/tripadvisor/search":
            params = urllib.parse.parse_qs(parsed.query)
            city = (params.get("city") or [""])[0].strip()
            keyword = (params.get("keyword") or ["景点"])[0].strip()
            category = (params.get("category") or ["attractions"])[0].strip()
            limit = int((params.get("limit") or ["6"])[0] or 6)
            limit = max(1, min(limit, 20))
            if not city:
                self.send_json(400, {"ok": False, "error": "city is required"})
                return
            try:
                self.send_json(200, tripadvisor_search(city, keyword, category, limit))
            except Exception as exc:
                self.send_json(502, {
                    "ok": False,
                    "error": str(exc),
                    "trace": traceback.format_exc(limit=3),
                })
            return

        if parsed.path == "/api/tripadvisor/reviews":
            params = urllib.parse.parse_qs(parsed.query)
            city = (params.get("city") or [""])[0].strip()
            name = (params.get("name") or [""])[0].strip()
            category = (params.get("category") or ["attractions"])[0].strip()
            content_id = (params.get("contentId") or params.get("content_id") or [""])[0].strip()
            limit = int((params.get("limit") or ["8"])[0] or 8)
            limit = max(1, min(limit, 20))
            if not city and not content_id:
                self.send_json(400, {"ok": False, "error": "city or contentId is required"})
                return
            try:
                self.send_json(200, tripadvisor_reviews(city, name, category, content_id, limit))
            except Exception as exc:
                self.send_json(502, {
                    "ok": False,
                    "error": str(exc),
                    "trace": traceback.format_exc(limit=3),
                })
            return

        if parsed.path == "/api/tripadvisor/hotels":
            params = urllib.parse.parse_qs(parsed.query)
            city = (params.get("city") or [""])[0].strip()
            limit = int((params.get("limit") or ["3"])[0] or 3)
            limit = max(1, min(limit, 10))
            if not city:
                self.send_json(400, {"ok": False, "error": "city is required"})
                return
            try:
                self.send_json(200, tripadvisor_hotels(city, limit))
            except Exception as exc:
                self.send_json(502, {
                    "ok": False,
                    "error": str(exc),
                    "trace": traceback.format_exc(limit=3),
                })
            return

        if parsed.path == "/api/tripadvisor/destination":
            params = urllib.parse.parse_qs(parsed.query)
            city = (params.get("city") or [""])[0].strip()
            limit = int((params.get("limit") or ["6"])[0] or 6)
            limit = max(1, min(limit, 10))
            if not city:
                self.send_json(400, {"ok": False, "error": "city is required"})
                return
            try:
                self.send_json(200, tripadvisor_destination(city, limit))
            except Exception as exc:
                self.send_json(502, {
                    "ok": False,
                    "error": str(exc),
                    "trace": traceback.format_exc(limit=3),
                })
            return

        if parsed.path == "/api/destination/discover":
            params = urllib.parse.parse_qs(parsed.query)
            origin = (params.get("origin") or [""])[0].strip()
            month_raw = (params.get("month") or [""])[0].strip()
            limit = int((params.get("limit") or ["6"])[0] or 6)
            limit = max(1, min(limit, 8))
            try:
                month = int(month_raw) if month_raw else date.today().month
            except ValueError:
                month = date.today().month
            try:
                self.send_json(200, destination_discover(month, origin, limit))
            except Exception as exc:
                self.send_json(502, {
                    "ok": False,
                    "error": str(exc),
                    "trace": traceback.format_exc(limit=3),
                })
            return

        return super().do_GET()


def main():
    port = int(os.environ.get("PORT", "8787"))
    host = os.environ.get("HOST", "0.0.0.0")
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"AI Wanderer RapidAPI proxy: http://{host}:{port}/index.html")
    print(f"TripAdvisor host: {RAPIDAPI_HOST}")
    print(f"RapidAPI key configured: {bool(RAPIDAPI_KEY)}")
    server.serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
