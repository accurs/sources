import re
import json
import asyncio
import aiohttp
from typing import Any, Dict, Optional, Union, List
from bs4 import BeautifulSoup

REGION_MAP = {"AF":"Afghanistan","AX":"Åland Islands","AL":"Albania","DZ":"Algeria","AS":"American Samoa","AD":"Andorra","AO":"Angola","AI":"Anguilla","AQ":"Antarctica","AG":"Antigua and Barbuda","AR":"Argentina","AM":"Armenia","AW":"Aruba","AU":"Australia","AT":"Austria","AZ":"Azerbaijan","BS":"Bahamas","BH":"Bahrain","BD":"Bangladesh","BB":"Barbados","BY":"Belarus","BE":"Belgium","BZ":"Belize","BJ":"Benin","BM":"Bermuda","BT":"Bhutan","BO":"Bolivia","BA":"Bosnia and Herzegovina","BW":"Botswana","BR":"Brazil","IO":"British Indian Ocean Territory","BN":"Brunei Darussalam","BG":"Bulgaria","BF":"Burkina Faso","BI":"Burundi","KH":"Cambodia","CM":"Cameroon","CA":"Canada","CV":"Cabo Verde","KY":"Cayman Islands","CF":"Central African Republic","TD":"Chad","CL":"Chile","CN":"China","CX":"Christmas Island","CC":"Cocos (Keeling) Islands","CO":"Colombia","KM":"Comoros","CG":"Congo","CD":"Congo (Democratic Republic)","CK":"Cook Islands","CR":"Costa Rica","CI":"Côte d'Ivoire","HR":"Croatia","CU":"Cuba","CW":"Curaçao","CY":"Cyprus","CZ":"Czechia","DK":"Denmark","DJ":"Djibouti","DM":"Dominica","DO":"Dominican Republic","EC":"Ecuador","EG":"Egypt","SV":"El Salvador","GQ":"Equatorial Guinea","ER":"Eritrea","EE":"Estonia","SZ":"Eswatini","ET":"Ethiopia","FK":"Falkland Islands (Malvinas)","FO":"Faroe Islands","FJ":"Fiji","FI":"Finland","FR":"France","GF":"French Guiana","PF":"French Polynesia","TF":"French Southern Territories","GA":"Gabon","GM":"Gambia","GE":"Georgia","DE":"Germany","GH":"Ghana","GI":"Gibraltar","GR":"Greece","GL":"Greenland","GD":"Grenada","GP":"Guadeloupe","GU":"Guam","GT":"Guatemala","GG":"Guernsey","GN":"Guinea","GW":"Guinea-Bissau","GY":"Guyana","HT":"Haiti","VA":"Holy See","HN":"Honduras","HK":"Hong Kong","HU":"Hungary","IS":"Iceland","IN":"India","ID":"Indonesia","IR":"Iran","IQ":"Iraq","IE":"Ireland","IM":"Isle of Man","IL":"Israel","IT":"Italy","JM":"Jamaica","JP":"Japan","JE":"Jersey","JO":"Jordan","KZ":"Kazakhstan","KE":"Kenya","KI":"Kiribati","KP":"Korea (Democratic People's Republic)","KR":"Korea (Republic)","KW":"Kuwait","KG":"Kyrgyzstan","LA":"Lao People's Democratic Republic","LV":"Latvia","LB":"Lebanon","LS":"Lesotho","LR":"Liberia","LY":"Libya","LI":"Liechtenstein","LT":"Lithuania","LU":"Luxembourg","MO":"Macao","MG":"Madagascar","MW":"Malawi","MY":"Malaysia","MV":"Maldives","ML":"Mali","MT":"Malta","MH":"Marshall Islands","MQ":"Martinique","MR":"Mauritania","MU":"Mauritius","YT":"Mayotte","MX":"Mexico","FM":"Micronesia (Federated States)","MD":"Moldova (Republic)","MC":"Monaco","MN":"Mongolia","ME":"Montenegro","MS":"Montserrat","MA":"Morocco","MZ":"Mozambique","MM":"Myanmar","NA":"Namibia","NR":"Nauru","NP":"Nepal","NL":"Netherlands","NC":"New Caledonia","NZ":"New Zealand","NI":"Nicaragua","NE":"Niger","NG":"Nigeria","NU":"Niue","NF":"Norfolk Island","MP":"Northern Mariana Islands","NO":"Norway","OM":"Oman","PK":"Pakistan","PW":"Palau","PS":"Palestine, State of","PA":"Panama","PG":"Papua New Guinea","PY":"Paraguay","PE":"Peru","PH":"Philippines","PN":"Pitcairn","PL":"Polany","PT":"Portugal","PR":"Puerto Rico","QA":"Qatar","MK":"Republic of North Macedonia","RO":"Romania","RU":"Russian Federation","RW":"Rwanda","RE":"Réunion","BL":"Saint Barthélemy","SH":"Saint Helena, Ascension and Tristan da Cunha","KN":"Saint Kitts and Nevis","LC":"Saint Lucia","MF":"Saint Martin (French part)","PM":"Saint Pierre and Miquelon","VC":"Saint Vincent and the Grenadines","WS":"Samoa","SM":"San Marino","ST":"Sao Tome and Principe","SA":"Saudi Arabia","SN":"Senegal","RS":"Serbia","SC":"Seychelles","SL":"Sierra Leone","SG":"Singapore","SX":"Sint Maarten (Dutch part)","SK":"Slovakia","SI":"Slovenia","SB":"Solomon Islands","SO":"Somalia","ZA":"South Africa","GS":"South Georgia and the South Sandwich Islands","SS":"South Sudan","ES":"Spain","LK":"Sri Lanka","SD":"Sudan","SR":"Suriname","SJ":"Svalbard and Jan Mayen","SE":"Sweden","CH":"Switzerland","SY":"Syrian Arab Republic","TW":"Taiwan","TJ":"Tajikistan","TZ":"Tanzania, United Republic of","TH":"Thailand","TL":"Timor-Leste","TG":"Togo","TK":"Tokelau","TO":"Tonga","TT":"Trinidad and Tobago","TN":"Tunisia","TR":"Turkey","TM":"Turkmenistan","TC":"Turks and Caicos Islands","TV":"Tuvalu","UG":"Uganda","UA":"Ukraine","AE":"United Arab Emirates","GB":"United Kingdom","UM":"United States Minor Outlying Islands","US":"United States","UY":"Uruguay","UZ":"Uzbekistan","VU":"Vanuatu","VE":"Venezuela","VN":"Viet Nam","VG":"Virgin Islands (British)","VI":"Virgin Islands (U.S.)","WF":"Wallis and Futuna","EH":"Western Sahara","YE":"Yemen","ZM":"Zambia","ZW":"Zimbabwe"}

class AsyncTikTokExtractor:
    def __init__(self, max_concurrent_requests: int = 100):
        self.max_connections = max_concurrent_requests
        self.session = None
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.cookies = {}
        
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        }
        
        self.video_id_pattern = re.compile(
            r"https?://(?:www\.)?tiktok\.com/\S*/(?:video|photo)/(\d+)"
        )
        self.shortened_url_pattern = re.compile(
            r"https?://(?:www\.)?(?:vm\.tiktok\.com|tiktok\.com/t/[a-zA-Z0-9]+|vt\.tiktok\.com/[a-zA-Z0-9]+)"
        )

    def _load_cookies_manual(self, file_path: str) -> dict:
        cookies = {}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

                if isinstance(data, list):
                    for c in data:
                        name = c.get("name")
                        value = c.get("value")
                        if name and value:
                            cookies[name] = value
                elif isinstance(data, dict):
                    cookies = {k: v for k, v in data.items() if k and v}

            print(json.dumps(cookies, indent=2))

        except Exception as e:
            print(f"Error loading cookies: {e}")

        return cookies

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            limit=self.max_connections,
            limit_per_host=500,
            keepalive_timeout=120,
            enable_cleanup_closed=True,
            ttl_dns_cache=600,
            use_dns_cache=True
        )
        
        timeout = aiohttp.ClientTimeout(total=10, connect=3)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self.headers
        )
        
        try:
            self.cookies = self._load_cookies_manual("/root/heist-v3/heist/framework/dataprocessing/tiktok/tiktok_cookies.txt")
        except Exception as e:
            self.cookies = {}
            
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_item_id_from_url(self, url: str) -> Optional[int]:
        if not (match := self.video_id_pattern.match(url)) and not self.shortened_url_pattern.match(url):
            return None

        if not match:
            try:
                cookies = self.cookies if self.cookies else None
                async with self.session.get(url, cookies=cookies) as response:
                    if response.ok and (match := self.video_id_pattern.match(str(response.url))):
                        return int(match.group(1))
            except:
                return None
        else:
            return int(match.group(1))

    async def extract_video(self, url: str) -> Dict[str, Any]:
        async with self.semaphore:
            try:
                item_id = await self.get_item_id_from_url(url)
                if not item_id:
                    return {"error": "Invalid TikTok URL"}

                return await self.get_video(item_id)
            except Exception as e:
                return {"error": f"Failed to extract video: {str(e)}"}

    async def get_video(self, item_id: Union[str, int]) -> Dict[str, Any]:
        try:
            cookies = self.cookies if self.cookies else None
            async with self.session.get(
                f"https://www.tiktok.com/player/api/v1/items?item_ids={item_id}",
                cookies=cookies
            ) as response:
                if not response.ok:
                    return {"error": f"API request failed with status {response.status}"}

                data = await response.json()
                if not data.get("items"):
                    return {"error": "No video data found"}

                item = data["items"][0]
                
                result = {
                    "id": item.get("id"),
                    "desc": item.get("desc", ""),
                    "author_info": {
                        "nickname": item.get("author_info", {}).get("nickname", ""),
                        "unique_id": item.get("author_info", {}).get("unique_id", ""),
                        "avatar_url": item.get("author_info", {}).get("avatar_url_list", [""])[0]
                    },
                    "statistics_info": {
                        "comment_count": item.get("statistics_info", {}).get("comment_count", 0),
                        "digg_count": item.get("statistics_info", {}).get("digg_count", 0),
                        "share_count": item.get("statistics_info", {}).get("share_count", 0)
                    },
                    "url": f"https://www.tiktok.com/@{item.get('author_info', {}).get('unique_id', '')}/video/{item.get('id')}",
                    "is_image_post": item.get("aweme_type") == 150
                }
                
                if "video_info" in item and item["video_info"].get("url_list"):
                    result["video_url"] = item["video_info"]["url_list"][0]
                
                if "image_post_info" in item:
                    images = item["image_post_info"].get("images", [])
                    result["image_urls"] = [img.get("display_image", {}).get("url_list", [""])[0] for img in images]
                
                if "music_info" in item:
                    music = item["music_info"]
                    result["audio_title"] = music.get("title", "")
                    result["audio_author"] = music.get("author", "")
                
                if "statistics_info" in item:
                    result["view_count"] = item["statistics_info"].get("play_count", 0)
                
                return result
                
        except Exception as e:
            return {"error": f"Failed to get video: {str(e)}"}

    async def get_user(self, username: str) -> Dict[str, Any]:
        async with self.semaphore:
            try:
                headers = {
                    "Host": "www.tiktok.com",
                    "User-Agent": "Mozilla/5.0 (Linux; Android 8.0.0; Plume L2) AppleWebKit/537.36 Chrome/99.0.4844.88 Mobile Safari/537.36"
                }
                cookies = self.cookies if self.cookies else None
                async with self.session.get(f"https://www.tiktok.com/@{username}", headers=headers, cookies=cookies) as response:
                    if not response.ok:
                        return {"error": f"Failed to fetch user (HTTP {response.status})"}

                    html = await response.text()
                    
                    start_idx = html.index(
                        '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
                    ) + len('<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">')
                    end_idx = html.index("</script>", start_idx)
                    res_json = html[start_idx:end_idx]
                    json_response = json.loads(res_json)

                    if (
                        "__DEFAULT_SCOPE__" not in json_response
                        or json_response["__DEFAULT_SCOPE__"]
                        .get("webapp.user-detail", {})
                        .get("statusCode") == 10204
                    ):
                        return {"error": "Could not find user data"}

                    user_data = json_response["__DEFAULT_SCOPE__"]["webapp.user-detail"]
                    if not user_data.get("userInfo", {}).get("user"):
                        return {"error": "User data format invalid"}

                    user = user_data["userInfo"]["user"]
                    stats = user_data["userInfo"]["stats"]

                    bio_url = None

                    if user.get("bioLink") and isinstance(user.get("bioLink"), dict):
                        bio_url = user.get("bioLink", {}).get("link")

                    if not bio_url and user.get("signature"):
                        match = re.search(r"(https?://\S+)", user["signature"])
                        if match:
                            bio_url = match.group(1)

                    return {
                        "id": user.get("id", ""),
                        "unique_id": user.get("uniqueId", ""),
                        "nickname": user.get("nickname", ""),
                        "avatar_larger": user.get("avatarLarger", ""),
                        "signature": user.get("signature", ""),
                        "bio_url": bio_url or "",
                        "verified": user.get("verified", False),
                        "private_account": user.get("privateAccount", False),
                        "region_code": user.get("region", ""),
                        "region": REGION_MAP.get(user.get("region", ""), ""),
                        "stats": {
                            "follower_count": stats.get("followerCount", 0),
                            "following_count": stats.get("followingCount", 0),
                            "heart_count": stats.get("heart", 0),
                            "video_count": stats.get("videoCount", 0)
                        }
                    }

            except Exception as e:
                return {"error": f"Error fetching user data: {str(e)}"}

    async def extract_multiple_videos(self, urls: list[str]) -> list[Dict[str, Any]]:
        tasks = [self.extract_video(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)
