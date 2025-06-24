# encoding:utf-8
import json
import requests
import re
import os
import time
import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from common.tmp_dir import TmpDir
from plugins import *
import random
import urllib.parse

@plugins.register(
    name="SearchMusic",
    desire_priority=100,
    desc="输入关键词'点歌 歌曲名称'即可获取对应歌曲详情和播放链接",
    version="3.0",
    author="Lingyuzhou",
)
class SearchMusic(Plugin):
    # 定义不同音乐平台对应的appid映射
    PLATFORM_APPIDS = {
        "kugou": "wx79f2c4418704b4f8",    # 酷狗音乐
        "kuwo": "wxc305711a2a7ad71c",     # 酷我音乐
        "netease": "wx8dd6ecd81906fd84",  # 网易云音乐
        "qishui": "wx904fb3ecf62c7dea",   # 汽水音乐
        "kugou_mv": "wx72b795aca60ad321", # 酷狗MV
        "qq": "wx5aa333606550dfd5"        # QQ音乐
    }
    
    # 平台显示名称映射
    PLATFORM_DISPLAY_NAMES = {
        "kugou": {"prefix": "[酷狗]", "source": "酷狗音乐"},
        "kuwo": {"prefix": "[酷我]", "source": "酷我音乐"},
        "netease": {"prefix": "[网易]", "source": "网易云音乐"},
        "qishui": {"prefix": "[网易]", "source": "汽水音乐"},
        "kugou_mv": {"prefix": "[酷狗MV]", "source": "酷狗MV"},
        "qq": {"prefix": "[QQ]", "source": "QQ音乐"}
    }
    
    def __init__(self):
        super().__init__()
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        logger.info("[SearchMusic] inited.")

    def get_appid_by_url(self, music_url, platform=""):
        """
        根据音乐URL域名动态选择AppID
        解决AppID与音乐源不匹配的问题
        """
        if "kuwo.cn" in music_url:
            return self.PLATFORM_APPIDS["kuwo"]  # 酷我音乐AppID
        elif "kugou.com" in music_url:
            return self.PLATFORM_APPIDS["kugou"]  # 酷狗音乐AppID
        elif "music.163.com" in music_url or "netease" in music_url:
            return self.PLATFORM_APPIDS["netease"]  # 网易云音乐AppID
        elif "qishui" in music_url or "douyinpic.com" in music_url:
            return self.PLATFORM_APPIDS["qishui"]  # 汽水音乐AppID
        elif platform.lower() == "qq" and "kuwo.cn" in music_url:
            # QQ音乐API返回酷我链接时，使用酷我AppID
            logger.info(f"[SearchMusic] QQ音乐检测到酷我域名，使用酷我AppID: {music_url}")
            return self.PLATFORM_APPIDS["kuwo"]
        else:
            return self.PLATFORM_APPIDS.get(platform.lower(), "")

    def construct_music_appmsg(self, title, singer, url, thumb_url="", platform=""):
        """
        构造音乐分享卡片的appmsg XML
        :param title: 音乐标题
        :param singer: 歌手名
        :param url: 音乐播放链接
        :param thumb_url: 封面图片URL（可选）
        :param platform: 音乐平台（酷狗/网易/汽水/酷我/qq）
        :return: appmsg XML字符串
        """
        # 处理封面URL
        if thumb_url:
            # 确保URL是以http或https开头
            if not thumb_url.startswith(("http://", "https://")):
                thumb_url = "https://" + thumb_url.lstrip("/")
            # 强制将http协议转换为https协议（微信安全要求）
            elif thumb_url.startswith("http://"):
                thumb_url = thumb_url.replace("http://", "https://", 1)
            # 确保URL没有特殊字符
            thumb_url = thumb_url.replace("&", "&amp;")
                
        # 动态选择AppID：根据音乐URL域名选择匹配的AppID
        appid = self.get_appid_by_url(url, platform)
        
        # 获取平台显示信息
        platform_lower = platform.lower()
        platform_info = self.PLATFORM_DISPLAY_NAMES.get(platform_lower)
        if platform_info:
            display_title = f"{platform_info['prefix']} {title}"
            source_display_name = platform_info['source']
        else:
            display_title = title
            source_display_name = "音乐分享"
        
        # 确保URL没有特殊字符
        url = url.replace("&", "&amp;")
        
        # 记录AppID选择信息，便于调试
        logger.info(f"[SearchMusic] 平台: {platform}, URL域名: {url[:50]}..., 选择的AppID: {appid}")
        
        # 使用更简化的XML结构，但保留关键标签，并添加对应的appid
        xml = f"""<appmsg appid="{appid}" sdkver="0">
    <title>{display_title}</title>
    <des>{singer}</des>
    <action>view</action>
    <type>3</type>
    <showtype>0</showtype>
    <soundtype>0</soundtype>
    <mediatagname>音乐</mediatagname>
    <messageaction></messageaction>
    <content></content>
    <contentattr>0</contentattr>
    <url>{url}</url>
    <lowurl>{url}</lowurl>
    <dataurl>{url}</dataurl>
    <lowdataurl>{url}</lowdataurl>
    <appattach>
        <totallen>0</totallen>
        <attachid></attachid>
        <emoticonmd5></emoticonmd5>
        <fileext></fileext>
        <cdnthumburl>{thumb_url}</cdnthumburl>
        <cdnthumbaeskey></cdnthumbaeskey>
        <aeskey></aeskey>
    </appattach>
    <extinfo></extinfo>
    <sourceusername></sourceusername>
    <sourcedisplayname>{source_display_name}</sourcedisplayname>
    <thumburl>{thumb_url}</thumburl>
    <songalbumurl>{thumb_url}</songalbumurl>
    <songlyric></songlyric>
</appmsg>"""
        
        # 记录生成的XML，便于调试
        logger.debug(f"[SearchMusic] 生成的音乐卡片XML (平台: {platform}, appid: {appid}): {xml}")
        
        return xml

    def construct_mv_appmsg(self, title, singer, video_url, thumb_url="", platform="kugou_mv"):
        """
        构造MV分享卡片的appmsg XML
        :param title: MV标题
        :param singer: 歌手名
        :param video_url: MV播放链接
        :param thumb_url: 封面图片URL（可选）
        :param platform: 平台名称（默认为kugou_mv）
        :return: appmsg XML字符串
        """
        # 处理封面URL
        if thumb_url:
            # 确保URL是以http或https开头
            if not thumb_url.startswith(("http://", "https://")):
                thumb_url = "https://" + thumb_url.lstrip("/")
            # 强制将http协议转换为https协议（微信安全要求）
            elif thumb_url.startswith("http://"):
                thumb_url = thumb_url.replace("http://", "https://", 1)
            # 确保URL没有特殊字符
            thumb_url = thumb_url.replace("&", "&amp;")
        else:
            # 使用默认MV封面
            thumb_url = "https://p2.music.126.net/tGHU62DTszbFQ37W9qPHcw==/2002210674180197.jpg"
                
        # 根据平台获取对应的appid和显示信息
        platform_lower = platform.lower()
        appid = self.PLATFORM_APPIDS.get(platform_lower, "")
        
        # 获取平台显示信息
        platform_info = self.PLATFORM_DISPLAY_NAMES.get(platform_lower)
        if platform_info:
            display_title = f"{platform_info['prefix']} {title}"
            source_display_name = platform_info['source']
        else:
            display_title = title
            source_display_name = "MV分享"
        
        # 确保URL没有特殊字符
        video_url = video_url.replace("&", "&amp;")
        
        # 构造MV卡片XML，使用type=5表示视频类型
        xml = f"""<appmsg appid="{appid}" sdkver="0">
    <title>{display_title}</title>
    <des>{singer}</des>
    <action>view</action>
    <type>5</type>
    <showtype>0</showtype>
    <soundtype>0</soundtype>
    <mediatagname>视频</mediatagname>
    <messageaction></messageaction>
    <content></content>
    <contentattr>0</contentattr>
    <url>{video_url}</url>
    <lowurl>{video_url}</lowurl>
    <dataurl>{video_url}</dataurl>
    <lowdataurl>{video_url}</lowdataurl>
    <appattach>
        <totallen>0</totallen>
        <attachid></attachid>
        <emoticonmd5></emoticonmd5>
        <fileext>mp4</fileext>
        <cdnthumburl>{thumb_url}</cdnthumburl>
        <cdnthumbaeskey></cdnthumbaeskey>
        <aeskey></aeskey>
    </appattach>
    <extinfo></extinfo>
    <sourceusername></sourceusername>
    <sourcedisplayname>{source_display_name}</sourcedisplayname>
    <thumburl>{thumb_url}</thumburl>
    <songalbumurl>{thumb_url}</songalbumurl>
    <songlyric></songlyric>
</appmsg>"""
        
        # 记录生成的XML，便于调试
        logger.debug(f"[SearchMusic] 生成的MV卡片XML (平台: {platform}, appid: {appid}): {xml}")
        
        return xml

    def get_music_cover(self, platform, detail_url, song_name="", singer=""):
        """
        尝试获取歌曲封面图片URL
        :param platform: 平台名称（kugou, netease, qishui, kuwo等）
        :param detail_url: 详情页URL（可选）
        :param song_name: 歌曲名称（可选，用于备用搜索）
        :param singer: 歌手名称（可选，用于备用搜索）
        :return: 封面图片URL
        """
        default_cover = "https://p2.music.126.net/tGHU62DTszbFQ37W9qPHcw==/2002210674180197.jpg"
        
        try:
            # 根据平台选择不同的获取方式
            if platform == "kugou":
                # 尝试从酷狗音乐详情页获取封面
                try:
                    if detail_url:
                        response = requests.get(detail_url, timeout=10)
                        # 使用正则表达式提取封面URL
                        cover_pattern = r'<img.*?src="(https?://.*?\.jpg)".*?>'
                        match = re.search(cover_pattern, response.text)
                        if match:
                            cover_url = match.group(1)
                            logger.info(f"[SearchMusic] 从酷狗音乐详情页提取到封面: {cover_url}")
                            return cover_url
                except Exception as e:
                    logger.error(f"[SearchMusic] 从酷狗音乐详情页获取封面时出错: {e}")
                
                # 如果从详情页获取失败，尝试使用备用方法
                if song_name and singer:
                    try:
                        # 使用备用API
                        backup_url = f"https://mobilecdn.kugou.com/api/v3/search/song?keyword={song_name}%20{singer}&page=1&pagesize=1"
                        response = requests.get(backup_url, timeout=10)
                        data = response.json()
                        if data["status"] == 1 and data["data"]["total"] > 0:
                            song_info = data["data"]["info"][0]
                            hash_value = song_info["hash"]
                            album_id = song_info.get("album_id", "")
                            if album_id:
                                cover_url = f"https://imge.kugou.com/stdmusic/{album_id}.jpg"
                                logger.info(f"[SearchMusic] 使用酷狗音乐API获取到封面: {cover_url}")
                                return cover_url
                    except Exception as e:
                        logger.error(f"[SearchMusic] 使用酷狗音乐API获取封面时出错: {e}")
            
            elif platform == "qishui":
                # 汽水音乐封面已在API响应中提供，这里不需要额外处理
                # 如果需要备用方法，可以在这里添加
                pass
                
            elif platform == "kuwo":
                # 尝试从酷我音乐API获取封面
                try:
                    if song_name and singer:
                        # 使用酷我音乐API搜索歌曲
                        search_url = f"https://api.suyanw.cn/api/kw.php?msg={song_name}"
                        response = requests.get(search_url, timeout=10)
                        data = json.loads(response.text)
                        if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                            # 查找匹配的歌曲
                            for song in data["data"]:
                                if "singer" in song and singer.lower() in song["singer"].lower():
                                    if "pic" in song and song["pic"]:
                                        cover_url = song["pic"]
                                        logger.info(f"[SearchMusic] 使用酷我音乐API获取到封面: {cover_url}")
                                        return cover_url
                                    break
                except Exception as e:
                    logger.error(f"[SearchMusic] 使用酷我音乐API获取封面时出错: {e}")
            
            elif platform == "netease":
                # 尝试从网易云音乐API获取封面
                try:
                    if song_name and singer:
                        # 使用网易云音乐API搜索歌曲
                        search_url = f"https://music.163.com/api/search/get/web?csrf_token=hlpretag=&hlposttag=&s={song_name}&type=1&offset=0&total=true&limit=1"
                        response = requests.get(search_url, timeout=10)
                        data = response.json()
                        if "result" in data and "songs" in data["result"] and len(data["result"]["songs"]) > 0:
                            song_info = data["result"]["songs"][0]
                            if "al" in song_info and "picUrl" in song_info["al"]:
                                cover_url = song_info["al"]["picUrl"]
                                logger.info(f"[SearchMusic] 使用网易云音乐API获取到封面: {cover_url}")
                                return cover_url
                except Exception as e:
                    logger.error(f"[SearchMusic] 使用网易云音乐API获取封面时出错: {e}")
            
            elif platform == "qq":
                # 如果是QQ音乐，尝试直接从QQ音乐API获取封面
                if song_name and singer:
                    try:
                        # 直接使用QQ音乐API获取封面
                        search_url = f"https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w={urllib.parse.quote(f'{song_name} {singer}')}&format=json&p=1&n=1"
                        response = requests.get(search_url, timeout=10)
                        if response.status_code == 200:
                            data = json.loads(response.text)
                            if "data" in data and "song" in data["data"] and "list" in data["data"]["song"] and data["data"]["song"]["list"]:
                                song_info = data["data"]["song"]["list"][0]
                                if "albummid" in song_info:
                                    albummid = song_info["albummid"]
                                    cover_url = f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{albummid}.jpg"
                                    logger.info(f"[SearchMusic] 成功获取QQ音乐封面: {cover_url}")
                                    return cover_url
                    except Exception as e:
                        logger.error(f"[SearchMusic] 获取QQ音乐封面时出错: {e}")
                
                # 如果没有找到，返回默认封面
                logger.warning(f"[SearchMusic] 无法获取QQ音乐封面图片，使用默认封面: {song_name} - {singer}")
                return default_cover
            
            # 对于其他平台，尝试使用歌曲名称和歌手名称搜索封面
            if song_name and singer:
                # 尝试使用QQ音乐搜索API获取封面
                try:
                    search_url = f"https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w={urllib.parse.quote(f'{song_name} {singer}')}&format=json&p=1&n=1"
                    response = requests.get(search_url, timeout=10)
                    if response.status_code == 200:
                        data = json.loads(response.text)
                        if "data" in data and "song" in data["data"] and "list" in data["data"]["song"] and data["data"]["song"]["list"]:
                            song_info = data["data"]["song"]["list"][0]
                            if "albummid" in song_info:
                                albummid = song_info["albummid"]
                                cover_url = f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{albummid}.jpg"
                                logger.info(f"[SearchMusic] 使用QQ音乐API获取到封面: {cover_url}")
                                return cover_url
                except Exception as e:
                    logger.error(f"[SearchMusic] 使用QQ音乐API获取封面时出错: {e}")
            
            logger.warning(f"[SearchMusic] 无法获取封面图片，使用默认封面: {song_name} - {singer}")
            return default_cover
            
        except Exception as e:
            logger.error(f"[SearchMusic] 获取封面图片时出错: {e}")
            return default_cover

    def extract_cover_from_response(self, response_text):
        """
        从API返回的内容中提取封面图片URL
        :param response_text: API返回的文本内容
        :return: 封面图片URL或None
        """
        try:
            # 尝试解析为JSON格式（汽水音乐API）
            try:
                data = json.loads(response_text)
                if "cover" in data and data["cover"]:
                    cover_url = data["cover"]
                    # 检查是否是抖音域名的图片
                    if "douyinpic.com" in cover_url or "douyincdn.com" in cover_url:
                        logger.warning(f"[SearchMusic] 检测到抖音域名图片，可能无法在微信中正常显示: {cover_url}")
                        # 不再使用备用图片
                    logger.info(f"[SearchMusic] 从JSON中提取到封面URL: {cover_url}")
                    return cover_url
            except json.JSONDecodeError:
                # 不是JSON格式，继续使用文本解析方法
                pass
                
            # 查找 ±img=URL± 格式的封面图片（抖音API格式）
            img_pattern = r'±img=(https?://[^±]+)±'
            match = re.search(img_pattern, response_text)
            if match:
                cover_url = match.group(1)
                # 检查是否是抖音域名的图片
                if "douyinpic.com" in cover_url or "douyincdn.com" in cover_url:
                    logger.warning(f"[SearchMusic] 检测到抖音域名图片，可能无法在微信中正常显示: {cover_url}")
                    # 不再移除后缀，保留完整的URL
                logger.info(f"[SearchMusic] 从API响应中提取到封面图片: {cover_url}")
                return cover_url
            return None
        except Exception as e:
            logger.error(f"[SearchMusic] 提取封面图片时出错: {e}")
            return None

    def get_video_url(self, url):
        """
        验证视频URL是否有效并返回可用的视频链接
        :param url: 视频URL
        :return: 有效的视频URL或None
        """
        try:
            response = requests.get(url)
            response.raise_for_status()
            content_type = response.headers.get('Content-Type')
            if 'video' in content_type:
                logger.debug("[SearchMusic] 视频内容已检测")
                return response.url
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"[SearchMusic] 请求视频URL失败: {e}")
            return None

    def download_music(self, music_url, platform):
        """
        下载音乐文件并返回文件路径
        :param music_url: 音乐文件URL
        :param platform: 平台名称（用于文件名）
        :return: 音乐文件保存路径或None（如果下载失败）
        """
        try:
            # 检查URL是否有效
            if not music_url or not music_url.startswith('http'):
                logger.error(f"[SearchMusic] 无效的音乐URL: {music_url}")
                return None

            # 发送GET请求下载文件，添加超时和重试机制
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            for retry in range(3):  # 最多重试3次
                try:
                    response = requests.get(music_url, stream=True, headers=headers, timeout=30)
                    response.raise_for_status()  # 检查响应状态
                    break
                except requests.RequestException as e:
                    if retry == 2:  # 最后一次重试
                        logger.error(f"[SearchMusic] 下载音乐文件失败，重试次数已用完: {e}")
                        return None
                    logger.warning(f"[SearchMusic] 下载重试 {retry + 1}/3: {e}")
                    time.sleep(1)  # 等待1秒后重试
            
            # 使用TmpDir().path()获取正确的临时目录
            tmp_dir = TmpDir().path()
            
            # 生成唯一的文件名，包含时间戳和随机字符串
            timestamp = int(time.time())
            random_str = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=6))
            music_name = f"{platform}_music_{timestamp}_{random_str}.mp3"
            music_path = os.path.join(tmp_dir, music_name)
            
            # 保存文件，使用块写入以节省内存
            total_size = 0
            with open(music_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)
                        total_size += len(chunk)
            
            # 验证文件大小
            if total_size == 0:
                logger.error("[SearchMusic] 下载的文件大小为0")
                os.remove(music_path)  # 删除空文件
                return None
                
            logger.info(f"[SearchMusic] 音乐下载完成: {music_path}, 大小: {total_size/1024:.2f}KB")
            return music_path
            
        except Exception as e:
            logger.error(f"[SearchMusic] 下载音乐文件时出错: {e}")
            # 如果文件已创建，清理它
            if 'music_path' in locals() and os.path.exists(music_path):
                try:
                    os.remove(music_path)
                except Exception as clean_error:
                    logger.error(f"[SearchMusic] 清理失败的下载文件时出错: {clean_error}")
            return None

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type != ContextType.TEXT:
            return
            
        content = e_context["context"].content
        reply = Reply()
        reply.type = ReplyType.TEXT

        # 处理随机点歌命令
        if content.strip() == "随机点歌":
            url = "https://hhlqilongzhu.cn/api/wangyi_hot_review.php"
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    try:
                        data = json.loads(response.text)
                        if "code" in data and data["code"] == 200:
                            # 提取歌曲信息
                            title = data.get("song", "未知歌曲")
                            singer = data.get("singer", "未知歌手")
                            music_url = data.get("url", "")
                            thumb_url = data.get("img", "")
                            link = data.get("link", "")
                            
                            # 记录获取到的随机歌曲信息
                            logger.info(f"[SearchMusic] 随机点歌获取成功: {title} - {singer}")
                            
                            # 构造音乐分享卡片
                            appmsg = self.construct_music_appmsg(title, singer, music_url, thumb_url, "netease")
                            
                            # 返回APP消息类型
                            reply.type = ReplyType.APP
                            reply.content = appmsg
                        else:
                            reply.content = "随机点歌失败，请稍后重试"
                    except json.JSONDecodeError:
                        logger.error(f"[SearchMusic] 随机点歌API返回的不是有效的JSON: {response.text[:100]}...")
                        reply.content = "随机点歌失败，请稍后重试"
                else:
                    reply.content = "随机点歌失败，请稍后重试"
            except Exception as e:
                logger.error(f"[SearchMusic] 随机点歌错误: {e}")
                reply.content = "随机点歌失败，请稍后重试"

        # 处理随机听歌命令
        elif content.strip() == "随机听歌":
            url = "https://hhlqilongzhu.cn/api/wangyi_hot_review.php"
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    try:
                        data = json.loads(response.text)
                        if "code" in data and data["code"] == 200:
                            # 提取歌曲信息
                            title = data.get("song", "未知歌曲")
                            singer = data.get("singer", "未知歌手")
                            music_url = data.get("url", "")
                            
                            # 记录获取到的随机歌曲信息
                            logger.info(f"[SearchMusic] 随机听歌获取成功: {title} - {singer}")
                            
                            # 下载音乐文件
                            music_path = self.download_music(music_url, "netease")
                            
                            if music_path:
                                # 返回语音消息
                                reply.type = ReplyType.VOICE
                                reply.content = music_path
                            else:
                                reply.type = ReplyType.TEXT
                                reply.content = "音乐文件下载失败，请稍后重试"
                        else:
                            reply.content = "随机听歌失败，请稍后重试"
                    except json.JSONDecodeError:
                        logger.error(f"[SearchMusic] 随机听歌API返回的不是有效的JSON: {response.text[:100]}...")
                        reply.content = "随机听歌失败，请稍后重试"
                else:
                    reply.content = "随机听歌失败，请稍后重试"
            except Exception as e:
                logger.error(f"[SearchMusic] 随机听歌错误: {e}")
                reply.content = "随机听歌失败，请稍后重试"

        # 处理酷狗点歌命令（搜索歌曲列表）
        elif content.startswith("酷狗点歌 "):
            song_name = content[5:].strip()  # 去除多余空格
            if not song_name:
                reply.content = "请输入要搜索的歌曲名称"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            # 检查是否包含序号（新增的详情获取功能）
            params = song_name.split()
            if len(params) == 2 and params[1].isdigit():
                song_name, song_number = params
                url = f"https://www.hhlqilongzhu.cn/api/dg_kgmusic.php?gm={song_name}&n={song_number}"
                try:
                    response = requests.get(url, timeout=10)
                    content = response.text
                    song_info = content.split('\n')
                    
                    if len(song_info) >= 4:  # 确保有足够的信息行
                        # 提取歌曲信息
                        title = song_info[1].replace("歌名：", "").strip()
                        singer = song_info[2].replace("歌手：", "").strip()
                        detail_url = song_info[3].replace("歌曲详情页：", "").strip()
                        music_url = song_info[4].replace("播放链接：", "").strip()
                        
                        # 尝试从响应中提取封面图片URL
                        thumb_url = self.extract_cover_from_response(content)
                        
                        # 如果从响应中没有提取到封面，尝试从详情页获取
                        if not thumb_url:
                            thumb_url = self.get_music_cover("kugou", detail_url, title, singer)
                        
                        # 构造音乐分享卡片
                        appmsg = self.construct_music_appmsg(title, singer, music_url, thumb_url, "kugou")
                        
                        # 返回APP消息类型
                        reply.type = ReplyType.APP
                        reply.content = appmsg
                    else:
                        reply.content = "未找到该歌曲，请确认歌名和序号是否正确"
                except Exception as e:
                    logger.error(f"[SearchMusic] 酷狗点歌详情错误: {e}")
                    reply.content = "获取失败，请稍后重试"
            else:
                # 原有的搜索歌曲列表功能
                url = f"https://www.hhlqilongzhu.cn/api/dg_kgmusic.php?gm={song_name}&n="
                try:
                    response = requests.get(url, timeout=10)
                    songs = response.text.strip().split('\n')
                    if songs and len(songs) > 1:  # 确保有搜索结果
                        reply_content = " 为你在酷狗音乐库中找到以下歌曲：\n\n"
                        for song in songs:
                            if song.strip():  # 确保不是空行
                                reply_content += f"{song}\n"
                        reply_content += f"\n请发送「酷狗点歌 {song_name} 序号」获取歌曲详情\n或发送「酷狗听歌 {song_name} 序号」来播放对应歌曲"
                    else:
                        reply_content = "未找到相关歌曲，请换个关键词试试"
                    reply.content = reply_content
                except Exception as e:
                    logger.error(f"[SearchMusic] 酷狗点歌错误: {e}")
                    reply.content = "搜索失败，请稍后重试"

        # 处理网易点歌命令（搜索歌曲列表）
        elif content.startswith("网易点歌 "):
            song_name = content[5:].strip()
            if not song_name:
                reply.content = "请输入要搜索的歌曲名称"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            # 检查是否包含序号（新增的详情获取功能）
            params = song_name.split()
            if len(params) == 2 and params[1].isdigit():
                song_name, song_number = params
                url = f"https://www.hhlqilongzhu.cn/api/dg_wyymusic.php?gm={song_name}&n={song_number}"
                try:
                    response = requests.get(url, timeout=10)
                    content = response.text
                    song_info = content.split('\n')
                    
                    if len(song_info) >= 4:  # 确保有足够的信息行
                        # 提取歌曲信息
                        title = song_info[1].replace("歌名：", "").strip()
                        singer = song_info[2].replace("歌手：", "").strip()
                        detail_url = song_info[3].replace("歌曲详情页：", "").strip()
                        music_url = song_info[4].replace("播放链接：", "").strip()
                        
                        # 尝试从响应中提取封面图片URL
                        thumb_url = self.extract_cover_from_response(content)
                        
                        # 如果从响应中没有提取到封面，尝试从详情页获取
                        if not thumb_url:
                            thumb_url = self.get_music_cover("netease", detail_url, title, singer)
                        
                        # 构造音乐分享卡片
                        appmsg = self.construct_music_appmsg(title, singer, music_url, thumb_url, "netease")
                        
                        # 返回APP消息类型
                        reply.type = ReplyType.APP
                        reply.content = appmsg
                    else:
                        reply.content = "未找到该歌曲，请确认歌名和序号是否正确"
                except Exception as e:
                    logger.error(f"[SearchMusic] 网易点歌详情错误: {e}")
                    reply.content = "获取失败，请稍后重试"
            else:
                # 原有的搜索歌曲列表功能
                url = f"https://www.hhlqilongzhu.cn/api/dg_wyymusic.php?gm={song_name}&n=&num=20"
                try:
                    response = requests.get(url, timeout=10)
                    songs = response.text.strip().split('\n')
                    if songs and len(songs) > 1:  # 确保有搜索结果
                        reply_content = " 为你在网易音乐库中找到以下歌曲：\n\n"
                        for song in songs:
                            if song.strip():  # 确保不是空行
                                reply_content += f"{song}\n"
                        reply_content += f"\n请发送「网易点歌 {song_name} 序号」获取歌曲详情\n或发送「网易听歌 {song_name} 序号」来播放对应歌曲"
                    else:
                        reply_content = "未找到相关歌曲，请换个关键词试试"
                    reply.content = reply_content
                except Exception as e:
                    logger.error(f"[SearchMusic] 网易点歌错误: {e}")
                    reply.content = "搜索失败，请稍后重试"

        # 处理汽水点歌命令
        elif content.startswith("汽水点歌 "):
            song_name = content[5:].strip()
            
            if not song_name:
                reply.content = "请输入要搜索的歌曲名称"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            # 检查是否包含序号（详情获取功能）
            params = song_name.split()
            if len(params) == 2 and params[1].isdigit():
                song_name, song_number = params
                url = f"https://hhlqilongzhu.cn/api/dg_qishuimusic.php?msg={song_name}&n={song_number}"
                try:
                    response = requests.get(url, timeout=10)
                    content = response.text
                    
                    # 尝试解析JSON响应
                    try:
                        data = json.loads(content)
                        if "title" in data and "singer" in data and "music" in data:
                            title = data["title"]
                            singer = data["singer"]
                            music_url = data["music"]
                            
                            # 提取封面图片URL
                            thumb_url = ""
                            if "cover" in data and data["cover"]:
                                thumb_url = data["cover"]
                                # 检查是否是抖音域名的图片
                                if "douyinpic.com" in thumb_url or "douyincdn.com" in thumb_url:
                                    logger.warning(f"[SearchMusic] 汽水点歌检测到抖音域名图片，可能无法在微信中正常显示: {thumb_url}")
                                    # 不再使用备用图片
                                    thumb_url = thumb_url
                            
                            # 如果没有提取到封面，尝试从详情页获取
                            if not thumb_url:
                                thumb_url = self.get_music_cover("qishui", "", title, singer)
                            
                            # 记录封面URL信息，便于调试
                            logger.info(f"[SearchMusic] 汽水点歌封面URL: {thumb_url}")
                            
                            # 构造音乐分享卡片
                            appmsg = self.construct_music_appmsg(title, singer, music_url, thumb_url, "qishui")
                            
                            # 返回APP消息类型
                            reply.type = ReplyType.APP
                            reply.content = appmsg
                        else:
                            reply.content = "未找到该歌曲，请确认歌名和序号是否正确"
                    except json.JSONDecodeError:
                        logger.error(f"[SearchMusic] 汽水音乐API返回的不是有效的JSON: {content[:100]}...")
                        reply.content = "获取失败，请稍后重试"
                        
                except Exception as e:
                    logger.error(f"[SearchMusic] 汽水点歌详情错误: {e}")
                    reply.content = "获取失败，请稍后重试"
            else:
                # 搜索歌曲列表功能
                url = f"https://hhlqilongzhu.cn/api/dg_qishuimusic.php?msg={song_name}"
                try:
                    response = requests.get(url, timeout=10)
                    content = response.text.strip()
                    
                    # 尝试解析JSON响应
                    try:
                        data = json.loads(content)
                        # 检查是否返回了歌曲列表
                        if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                            # 新格式：包含完整歌曲列表的JSON
                            reply_content = " 为你在汽水音乐库中找到以下歌曲：\n\n"
                            for song in data["data"]:
                                if "n" in song and "title" in song and "singer" in song:
                                    reply_content += f"{song['n']}. {song['title']} - {song['singer']}\n"
                            
                            reply_content += f"\n请发送「汽水点歌 {song_name} 序号」获取歌曲详情\n或发送「汽水听歌 {song_name} 序号」来播放对应歌曲"
                        elif "title" in data and "singer" in data:
                            # 旧格式：只返回单个歌曲的JSON
                            reply_content = " 为你在汽水音乐库中找到以下歌曲：\n\n"
                            reply_content += f"1. {data['title']} - {data['singer']}\n"
                            reply_content += f"\n请发送「汽水点歌 {song_name} 1」获取歌曲详情\n或发送「汽水听歌 {song_name} 1」来播放对应歌曲"
                        else:
                            reply_content = "未找到相关歌曲，请换个关键词试试"
                    except json.JSONDecodeError:
                        # 如果不是JSON，尝试使用正则表达式解析文本格式的结果
                        pattern = r"(\d+)\.\s+(.*?)\s+-\s+(.*?)$"
                        matches = re.findall(pattern, content, re.MULTILINE)
                        
                        if matches:
                            reply_content = " 为你在汽水音乐库中找到以下歌曲：\n\n"
                            for match in matches:
                                number, title, singer = match
                                reply_content += f"{number}. {title} - {singer}\n"
                            
                            reply_content += f"\n请发送「汽水点歌 {song_name} 序号」获取歌曲详情\n或发送「汽水听歌 {song_name} 序号」来播放对应歌曲"
                        else:
                            logger.error(f"[SearchMusic] 汽水音乐API返回格式无法解析: {content[:100]}...")
                            reply_content = "搜索结果解析失败，请稍后重试"
                    
                    reply.content = reply_content
                except Exception as e:
                    logger.error(f"[SearchMusic] 汽水点歌错误: {e}")
                    reply.content = "搜索失败，请稍后重试"


        # 处理酷狗听歌命令
        elif content.startswith("酷狗听歌 "):
            params = content[5:].strip().split()
            if len(params) != 2:
                reply.content = "请输入正确的格式：酷狗听歌 歌曲名称 序号"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            song_name, song_number = params
            if not song_number.isdigit():
                reply.content = "请输入正确的歌曲序号（纯数字）"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            url = f"https://www.hhlqilongzhu.cn/api/dg_kgmusic.php?gm={song_name}&n={song_number}"
            
            try:
                response = requests.get(url, timeout=10)
                content = response.text
                song_info = content.split('\n')
                
                if len(song_info) >= 4:  # 确保有足够的信息行
                    # 获取音乐文件URL（在第4行），并去除可能的"播放链接："前缀
                    music_url = song_info[4].strip()
                    if "播放链接：" in music_url:
                        music_url = music_url.split("播放链接：")[1].strip()
                    
                    # 下载音乐文件
                    music_path = self.download_music(music_url, "kugou")
                    
                    if music_path:
                        # 返回语音消息
                        reply.type = ReplyType.VOICE
                        reply.content = music_path
                    else:
                        reply.type = ReplyType.TEXT
                        reply.content = "音乐文件下载失败，请稍后重试"
                else:
                    reply.content = "未找到该歌曲，请确认歌名和序号是否正确"

            except Exception as e:
                logger.error(f"[SearchMusic] 酷狗听歌错误: {e}")
                reply.content = "获取失败，请稍后重试"

        # 处理网易听歌命令
        elif content.startswith("网易听歌 "):
            params = content[5:].strip().split()
            if len(params) != 2:
                reply.content = "请输入正确的格式：网易听歌 歌曲名称 序号"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            song_name, song_number = params
            if not song_number.isdigit():
                reply.content = "请输入正确的歌曲序号（纯数字）"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            url = f"https://www.hhlqilongzhu.cn/api/dg_wyymusic.php?gm={song_name}&n={song_number}"
            
            try:
                response = requests.get(url, timeout=10)
                content = response.text
                
                # 解析返回内容
                song_info = content.split('\n')
                
                if len(song_info) >= 4:  # 确保有足够的信息行
                    # 获取音乐文件URL（在第4行），并去除可能的"播放链接："前缀
                    music_url = song_info[4].strip()
                    if "播放链接：" in music_url:
                        music_url = music_url.split("播放链接：")[1].strip()
                    
                    # 下载音乐文件
                    music_path = self.download_music(music_url, "netease")
                    
                    if music_path:
                        # 返回语音消息
                        reply.type = ReplyType.VOICE
                        reply.content = music_path
                    else:
                        reply.type = ReplyType.TEXT
                        reply.content = "音乐文件下载失败，请稍后重试"
                else:
                    reply.content = "未找到该歌曲，请确认歌名和序号是否正确"

            except Exception as e:
                logger.error(f"[SearchMusic] 网易听歌错误: {e}")
                reply.content = "获取失败，请稍后重试"

        # 处理酷我点歌命令
        elif content.startswith("酷我点歌 "):
            song_name = content[5:].strip()
            
            if not song_name:
                reply.content = "请输入要搜索的歌曲名称"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            # 检查是否包含序号（详情获取功能）
            params = song_name.split()
            if len(params) == 2 and params[1].isdigit():
                song_name, song_number = params
                url = f"https://hhlqilongzhu.cn/api/dg_kuwomusic.php?msg={song_name}&n={song_number}"
                try:
                    response = requests.get(url, timeout=10)
                    content = response.text
                    
                    # 解析文本格式的响应
                    song_info = content.split('\n')
                    
                    if len(song_info) >= 4:  # 确保有足够的信息行
                        # 提取歌曲信息
                        thumb_url = ""
                        title = ""
                        singer = ""
                        music_url = ""
                        
                        # 解析每一行信息
                        for line in song_info:
                            line = line.strip()
                            if line.startswith("±img="):
                                thumb_url = line.replace("±img=", "").replace("±", "").strip()
                            elif line.startswith("歌名："):
                                title = line.replace("歌名：", "").strip()
                            elif line.startswith("歌手："):
                                singer = line.replace("歌手：", "").strip()
                            elif line.startswith("播放链接："):
                                music_url = line.replace("播放链接：", "").strip()
                        
                        if title and singer and music_url:
                            # 记录歌曲信息，便于调试
                            logger.info(f"[SearchMusic] 酷我点歌信息: {title} - {singer}, 封面: {thumb_url}, URL: {music_url}")
                            
                            # 构造音乐分享卡片
                            appmsg = self.construct_music_appmsg(title, singer, music_url, thumb_url, "kuwo")
                            
                            # 返回APP消息类型
                            reply.type = ReplyType.APP
                            reply.content = appmsg
                        else:
                            reply.content = "解析歌曲信息失败，请稍后重试"
                    else:
                        reply.content = "未找到该歌曲，请确认歌名和序号是否正确"
                except Exception as e:
                    logger.error(f"[SearchMusic] 酷我点歌详情错误: {e}")
                    reply.content = "获取失败，请稍后重试"
            else:
                # 搜索歌曲列表功能
                url = f"https://hhlqilongzhu.cn/api/dg_kuwomusic.php?msg={song_name}"
                try:
                    response = requests.get(url, timeout=10)
                    content = response.text.strip()
                    
                    # 解析返回的歌曲列表
                    songs = content.strip().split('\n')
                    if songs and len(songs) > 0:
                        reply_content = " 为你在酷我音乐库中找到以下歌曲：\n\n"
                        for song in songs:
                            if song.strip():
                                reply_content += f"{song}\n"
                        
                        reply_content += f"\n请发送「酷我点歌 {song_name} 序号」获取歌曲详情\n或发送「酷我听歌 {song_name} 序号」来播放对应歌曲"
                    else:
                        reply_content = "未找到相关歌曲，请换个关键词试试"
                    
                    reply.content = reply_content
                except Exception as e:
                    logger.error(f"[SearchMusic] 酷我点歌错误: {e}")
                    reply.content = "搜索失败，请稍后重试"

        # 处理汽水听歌命令
        elif content.startswith("汽水听歌 "):
            params = content[5:].strip().split()
            if len(params) != 2:
                reply.content = "请输入正确的格式：汽水听歌 歌曲名称 序号"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            song_name, song_number = params
            if not song_number.isdigit():
                reply.content = "请输入正确的歌曲序号（纯数字）"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            url = f"https://hhlqilongzhu.cn/api/dg_qishuimusic.php?msg={song_name}&n={song_number}"
            
            try:
                response = requests.get(url, timeout=10)
                content = response.text
                
                # 尝试解析JSON响应
                try:
                    data = json.loads(content)
                    if "music" in data and data["music"]:
                        music_url = data["music"]
                        
                        # 下载音乐文件
                        music_path = self.download_music(music_url, "qishui")
                        
                        if music_path:
                            # 返回语音消息
                            reply.type = ReplyType.VOICE
                            reply.content = music_path
                        else:
                            reply.type = ReplyType.TEXT
                            reply.content = "音乐文件下载失败，请稍后重试"
                    else:
                        reply.content = "未找到该歌曲的播放链接，请确认歌名和序号是否正确"
                except json.JSONDecodeError:
                    logger.error(f"[SearchMusic] 汽水音乐API返回的不是有效的JSON: {content[:100]}...")
                    reply.content = "获取失败，请稍后重试"
                    
            except Exception as e:
                logger.error(f"[SearchMusic] 汽水听歌错误: {e}")
                reply.content = "获取失败，请稍后重试"

        # 处理酷我听歌命令
        elif content.startswith("酷我听歌 "):
            params = content[5:].strip().split()
            if len(params) != 2:
                reply.content = "请输入正确的格式：酷我听歌 歌曲名称 序号"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            song_name, song_number = params
            if not song_number.isdigit():
                reply.content = "请输入正确的歌曲序号（纯数字）"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            url = f"https://hhlqilongzhu.cn/api/dg_kuwomusic.php?msg={song_name}&n={song_number}"
            
            try:
                response = requests.get(url, timeout=10)
                content = response.text
                
                # 尝试解析JSON响应
                try:
                    data = json.loads(content)
                    if "url" in data and data["url"]:
                        music_url = data["url"]
                        
                        # 下载音乐文件
                        music_path = self.download_music(music_url, "kuwo")
                        
                        if music_path:
                            # 返回语音消息
                            reply.type = ReplyType.VOICE
                            reply.content = music_path
                        else:
                            reply.type = ReplyType.TEXT
                            reply.content = "音乐文件下载失败，请稍后重试"
                    else:
                        reply.content = "未找到该歌曲的播放链接，请确认歌名和序号是否正确"
                except json.JSONDecodeError:
                    # 如果不是JSON，尝试解析文本格式
                    logger.info(f"[SearchMusic] 酷我音乐API返回文本格式响应，尝试解析: {content[:100]}...")
                    
                    # 解析文本格式的响应
                    song_info = content.split('\n')
                    music_url = ""
                    
                    for line in song_info:
                        line = line.strip()
                        if line.startswith("播放链接：") or "播放链接：" in line:
                            # 提取播放链接，可能包含在<a>标签中
                            if "<a href=" in line:
                                match = re.search(r'<a href="([^"]+)"', line)
                                if match:
                                    music_url = match.group(1)
                            else:
                                music_url = line.replace("播放链接：", "").strip()
                            break
                    
                    if music_url:
                        # 下载音乐文件
                        music_path = self.download_music(music_url, "kuwo")
                        
                        if music_path:
                            # 返回语音消息
                            reply.type = ReplyType.VOICE
                            reply.content = music_path
                        else:
                            reply.type = ReplyType.TEXT
                            reply.content = "音乐文件下载失败，请稍后重试"
                    else:
                        reply.content = "未找到该歌曲的播放链接，请确认歌名和序号是否正确"
                    
            except Exception as e:
                logger.error(f"[SearchMusic] 酷我听歌错误: {e}")
                reply.content = "获取失败，请稍后重试"

        # 处理酷狗MV命令
        elif content.startswith("酷狗MV "):
            song_name = content[4:].strip()
            
            if not song_name:
                reply.content = "请输入要搜索的MV名称"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            # 检查是否包含序号（详情获取功能）
            params = song_name.split()
            if len(params) == 2 and params[1].isdigit():
                song_name, song_number = params
                url = f"https://api.317ak.com/API/yljk/kgmv/kgmv.php?msg={song_name}&n={song_number}"
                try:
                    response = requests.get(url, timeout=10)
                    content = response.text
                    
                    # 尝试解析JSON响应
                    try:
                        data = json.loads(content)
                        if "code" in data and data["code"] == 1 and "data" in data:
                            mv_data = data["data"]
                            if "name" in mv_data and "singer" in mv_data and "url" in mv_data:
                                title = mv_data["name"]
                                singer = mv_data["singer"]
                                video_url = mv_data["url"]
                                
                                # 获取MV封面图片
                                thumb_url = mv_data.get('cover', '')
                                
                                # 验证视频URL是否有效
                                valid_url = self.get_video_url(video_url)
                                if valid_url:
                                    # 记录MV信息，便于调试
                                    logger.info(f"[SearchMusic] 酷狗MV详情: {title} - {singer}, URL: {valid_url}, 封面: {thumb_url}")
                                    
                                    # 构造MV分享卡片
                                    appmsg = self.construct_mv_appmsg(title, singer, valid_url, thumb_url, "kugou_mv")
                                    
                                    # 返回APP消息类型
                                    reply.type = ReplyType.APP
                                    reply.content = appmsg
                                else:
                                    reply.content = "视频链接无效，请稍后重试或尝试其他MV"
                            else:
                                reply.content = "未找到该MV的播放链接，请确认歌名和序号是否正确"
                        else:
                            reply.content = "未找到该MV，请确认歌名和序号是否正确"
                    except json.JSONDecodeError:
                        logger.error(f"[SearchMusic] 酷狗MV API返回的不是有效的JSON: {content[:100]}...")
                        reply.content = "获取失败，请稍后重试"
                        
                except Exception as e:
                    logger.error(f"[SearchMusic] 酷狗MV详情错误: {e}")
                    reply.content = "获取失败，请稍后重试"
            else:
                # 搜索MV列表功能
                url = f"https://api.317ak.com/API/yljk/kgmv/kgmv.php?msg={song_name}"
                try:
                    response = requests.get(url, timeout=10)
                    content = response.text.strip()
                    
                    # 尝试解析JSON响应
                    try:
                        data = json.loads(content)
                        # 检查是否返回了MV列表
                        if "code" in data and data["code"] == 1 and "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                            # 包含完整MV列表的JSON
                            reply_content = " 为你在酷狗MV库中找到以下视频：\n\n"
                            
                            # 为每个MV添加序号
                            for i, mv in enumerate(data["data"], 1):
                                if "name" in mv and "singer" in mv:
                                    reply_content += f"{i}. {mv['name']} - {mv['singer']}\n"
                            
                            reply_content += f"\n请发送「酷狗MV {song_name} 序号」获取对应MV视频"
                        else:
                            reply_content = "未找到相关MV，请换个关键词试试"
                    except json.JSONDecodeError:
                        logger.error(f"[SearchMusic] 酷狗MV API返回的不是有效的JSON: {content[:100]}...")
                        reply_content = "搜索结果解析失败，请稍后重试"
                    
                    reply.content = reply_content
                except Exception as e:
                    logger.error(f"[SearchMusic] 酷狗MV搜索错误: {e}")
                    reply.content = "搜索失败，请稍后重试"

        # 处理QQ点歌命令（搜索歌曲列表）
        elif content.startswith("QQ点歌 ") or content.startswith("qq点歌 "):
            song_name = content[4:].strip()  # 去除多余空格
            if not song_name:
                reply.content = "请输入要搜索的歌曲名称"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            # 检查是否包含序号（详情获取功能）
            params = song_name.split()
            if len(params) == 2 and params[1].isdigit():
                song_name, song_number = params
                # 修改URL，添加type=json参数获取JSON格式响应
                url = f"https://hhlqilongzhu.cn/api/dg_QQmusicflac.php?msg={song_name}&n={song_number}&type=json"
                try:
                    response = requests.get(url, timeout=10)
                    content = response.text
                    
                    # 尝试解析JSON响应
                    try:
                        data = json.loads(content)
                        # 检查data字段中的信息
                        if "data" in data and isinstance(data["data"], dict):
                            data_obj = data["data"]
                            if "song_name" in data_obj and "song_singer" in data_obj and "music_url" in data_obj:
                                title = data_obj["song_name"]
                                singer = data_obj["song_singer"]
                                music_url = data_obj["music_url"]
                                
                                # 提取封面图片URL
                                thumb_url = ""
                                if "cover" in data_obj and data_obj["cover"]:
                                    thumb_url = data_obj["cover"]
                                    logger.info(f"[SearchMusic] 从QQ音乐API直接获取到封面URL: {thumb_url}")
                                
                                # 如果没有提取到封面，尝试从详情页获取或使用通用方法获取
                                if not thumb_url:
                                    detail_url = data_obj.get("link", "")
                                    thumb_url = self.get_music_cover("qq", detail_url, title, singer)
                                
                                # 记录封面URL信息，便于调试
                                logger.info(f"[SearchMusic] QQ点歌封面URL: {thumb_url}")
                                
                                # 构造音乐分享卡片
                                appmsg = self.construct_music_appmsg(title, singer, music_url, thumb_url, "qq")
                                
                                # 返回APP消息类型
                                reply.type = ReplyType.APP
                                reply.content = appmsg
                            else:
                                reply.content = "未找到该歌曲，请确认歌名和序号是否正确"
                        
                        # 如果data字段不存在或解析失败，尝试直接获取字段
                        elif "title" in data and "singer" in data and "url" in data:
                            title = data["title"]
                            singer = data["singer"]
                            music_url = data["url"]
                            
                            # 提取封面图片URL
                            thumb_url = ""
                            if "cover" in data and data["cover"]:
                                thumb_url = data["cover"]
                            elif "pic" in data and data["pic"]:
                                thumb_url = data["pic"]
                            
                            # 如果没有提取到封面，尝试从详情页获取或使用通用方法获取
                            if not thumb_url:
                                detail_url = data.get("link", "")
                                thumb_url = self.get_music_cover("qq", detail_url, title, singer)
                            
                            # 记录封面URL信息，便于调试
                            logger.info(f"[SearchMusic] QQ点歌封面URL: {thumb_url}")
                            
                            # 构造音乐分享卡片
                            appmsg = self.construct_music_appmsg(title, singer, music_url, thumb_url, "qq")
                            
                            # 返回APP消息类型
                            reply.type = ReplyType.APP
                            reply.content = appmsg
                        else:
                            reply.content = "未找到该歌曲，请确认歌名和序号是否正确"
                    except json.JSONDecodeError:
                        # 尝试使用文本格式解析
                        song_info = content.split('\n')
                        if len(song_info) >= 4:  # 确保有足够的信息行
                            # 提取歌曲信息
                            title_line = next((line for line in song_info if line.startswith("歌名：")), "")
                            singer_line = next((line for line in song_info if line.startswith("歌手：")), "")
                            detail_line = next((line for line in song_info if line.startswith("歌曲详情页：")), "")
                            music_line = next((line for line in song_info if line.startswith("播放链接：")), "")
                            
                            if title_line and singer_line and music_line:
                                title = title_line.replace("歌名：", "").strip()
                                singer = singer_line.replace("歌手：", "").strip()
                                detail_url = detail_line.replace("歌曲详情页：", "").strip() if detail_line else ""
                                music_url = music_line.replace("播放链接：", "").strip()
                                
                                # 尝试从响应中提取封面图片URL
                                thumb_url = self.extract_cover_from_response(content)
                                
                                # 如果从响应中没有提取到封面，尝试从详情页获取
                                if not thumb_url and detail_url:
                                    thumb_url = self.get_music_cover("qq", detail_url, title, singer)
                                
                                # 如果仍然没有封面，使用QQ音乐封面获取方法
                                if not thumb_url:
                                    thumb_url = self.get_music_cover("qq", "", title, singer)
                                
                                # 构造音乐分享卡片
                                appmsg = self.construct_music_appmsg(title, singer, music_url, thumb_url, "qq")
                                
                                # 返回APP消息类型
                                reply.type = ReplyType.APP
                                reply.content = appmsg
                            else:
                                reply.content = "未找到该歌曲，请确认歌名和序号是否正确"
                        else:
                            reply.content = "获取失败，请稍后重试"
                        
                except Exception as e:
                    logger.error(f"[SearchMusic] QQ点歌详情错误: {e}")
                    reply.content = "获取失败，请稍后重试"
            else:
                # 使用修复后的QQ音乐搜索功能
                reply.content = self.fix_qq_music_search(song_name)

        # 处理QQ听歌命令
        elif content.startswith("QQ听歌 ") or content.startswith("qq听歌 "):
            params = content[4:].strip().split()
            if len(params) != 2:
                reply.content = "请输入正确的格式：QQ听歌 歌曲名称 序号"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            song_name, song_number = params
            if not song_number.isdigit():
                reply.content = "请输入正确的歌曲序号（纯数字）"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            # 修改URL，明确使用JSON格式响应，增加重试和更长的超时
            url = f"https://hhlqilongzhu.cn/api/dg_QQmusicflac.php?msg={urllib.parse.quote(song_name)}&n={song_number}&type=json"
            
            try:
                # 增加重试机制和更长的超时时间
                for retry in range(3):
                    try:
                        response = requests.get(url, timeout=15)
                        if response.status_code == 200:
                            break
                    except requests.RequestException as e:
                        if retry == 2:
                            logger.error(f"[SearchMusic] QQ听歌网络错误，重试失败: {e}")
                            reply.content = "获取失败，网络连接错误，请稍后重试"
                            e_context["reply"] = reply
                            e_context.action = EventAction.BREAK_PASS
                            return
                        logger.warning(f"[SearchMusic] QQ听歌重试 {retry+1}/3: {e}")
                        time.sleep(1)
                
                # 记录原始响应内容，便于调试
                logger.debug(f"[SearchMusic] QQ听歌原始响应: {response.text[:200]}...")
                
                # 尝试多种方式解析响应获取音乐URL
                music_url = None
                
                # 首先尝试解析JSON
                try:
                    data = json.loads(response.text)
                    # 检查标准JSON格式
                    if "data" in data and isinstance(data["data"], dict) and "music_url" in data["data"]:
                        music_url = data["data"]["music_url"]
                        logger.info(f"[SearchMusic] 从JSON data字段获取到QQ音乐URL: {music_url}")
                    # 检查简化的JSON格式
                    elif "url" in data and data["url"]:
                        music_url = data["url"]
                        logger.info(f"[SearchMusic] 从JSON url字段获取到QQ音乐URL: {music_url}")
                    elif "music_url" in data:
                        music_url = data["music_url"]
                        logger.info(f"[SearchMusic] 从JSON music_url字段获取到QQ音乐URL: {music_url}")
                except json.JSONDecodeError:
                    # 不是JSON格式，尝试文本格式解析
                    logger.warning("[SearchMusic] QQ听歌响应不是有效的JSON，尝试文本解析")
                
                # 如果JSON解析失败，尝试文本解析
                if not music_url:
                    # 尝试从文本中提取播放链接
                    music_pattern = r"播放链接：(https?://[^\s]+)"
                    match = re.search(music_pattern, response.text)
                    if match:
                        music_url = match.group(1)
                        logger.info(f"[SearchMusic] 从文本中提取到QQ音乐URL: {music_url}")
                
                # 最后一次尝试：如果以上都失败，重新请求纯文本格式
                if not music_url:
                    logger.warning("[SearchMusic] 尝试使用text格式重新获取QQ音乐链接")
                    text_url = f"https://hhlqilongzhu.cn/api/dg_QQmusicflac.php?msg={urllib.parse.quote(song_name)}&n={song_number}&type=text"
                    try:
                        text_response = requests.get(text_url, timeout=15)
                        if text_response.status_code == 200:
                            # 尝试从文本中提取播放链接
                            music_pattern = r"播放链接：(https?://[^\s]+)"
                            match = re.search(music_pattern, text_response.text)
                            if match:
                                music_url = match.group(1)
                                logger.info(f"[SearchMusic] 从文本格式重新获取到QQ音乐URL: {music_url}")
                    except Exception as e:
                        logger.error(f"[SearchMusic] 文本格式重新获取QQ音乐URL失败: {e}")
                
                # 检查是否成功获取到音乐URL
                if not music_url:
                    logger.error("[SearchMusic] 无法获取QQ音乐URL")
                    reply.content = "未找到该歌曲的播放链接，请确认歌名和序号是否正确"
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                    return
                
                # 下载音乐文件
                music_path = self.download_music(music_url, "qq")
                
                if music_path:
                    # 返回语音消息
                    reply.type = ReplyType.VOICE
                    reply.content = music_path
                else:
                    reply.type = ReplyType.TEXT
                    reply.content = "音乐文件下载失败，请稍后重试"
                    
            except Exception as e:
                logger.error(f"[SearchMusic] QQ听歌错误: {e}")
                reply.content = "获取失败，请稍后重试"

        else:
            return

        e_context["reply"] = reply
        e_context.action = EventAction.BREAK_PASS

    def fix_qq_music_search(self, song_name):
        """
        修复QQ音乐搜索功能，根据API文档使用正确的参数和返回格式处理
        :param song_name: 歌曲名称
        :return: 歌曲列表或错误信息
        """
        try:
            # 使用明确的type=text参数确保返回文本格式
            url = f"https://hhlqilongzhu.cn/api/dg_QQmusicflac.php?msg={urllib.parse.quote(song_name)}&n=&type=text"
            
            logger.info(f"[SearchMusic] 发送QQ音乐搜索请求: {url}")
            
            # 设置更长的超时时间，增加重试次数
            for retry in range(3):
                try:
                    response = requests.get(url, timeout=15)
                    if response.status_code == 200:
                        break
                except requests.RequestException as e:
                    if retry == 2:
                        logger.error(f"[SearchMusic] QQ音乐搜索网络错误，重试失败: {e}")
                        return "搜索失败，网络连接错误，请稍后重试"
                    logger.warning(f"[SearchMusic] QQ音乐搜索重试 {retry+1}/3: {e}")
                    time.sleep(1)
            
            # 检查响应是否为空
            if not response.text.strip():
                logger.error("[SearchMusic] QQ音乐搜索返回空响应")
                return "未找到相关歌曲，请换个关键词试试"
            
            # 记录返回的原始内容，便于调试
            logger.debug(f"[SearchMusic] QQ音乐搜索返回原始内容: {response.text[:200]}...")
            
            # 处理文本格式的响应
            songs = response.text.strip().split('\n')
            if not songs or len(songs) == 0:
                logger.warning("[SearchMusic] QQ音乐搜索未返回歌曲列表")
                return "未找到相关歌曲，请换个关键词试试"
            
            # 检查是否包含错误信息
            if len(songs) == 1 and ("错误" in songs[0] or "失败" in songs[0] or "找不到" in songs[0]):
                logger.warning(f"[SearchMusic] QQ音乐搜索返回错误: {songs[0]}")
                return "未找到相关歌曲，请换个关键词试试"
                
            # 返回格式化的结果
            reply_content = " 为你在QQ音乐库中找到以下歌曲：\n\n"
            for song in songs:
                if song.strip():  # 确保不是空行
                    reply_content += f"{song}\n"
            reply_content += f"\n请发送「QQ点歌 {song_name} 序号」获取歌曲详情\n或发送「QQ听歌 {song_name} 序号」来播放对应歌曲"
            
            return reply_content
            
        except Exception as e:
            logger.error(f"[SearchMusic] QQ音乐搜索异常: {e}")
            return "搜索失败，请稍后重试"

    def get_help_text(self, **kwargs):
        return (
            " 音乐搜索和播放功能：\n\n"
            "1. 酷狗音乐：\n"
            "   - 搜索歌单：发送「酷狗点歌 歌曲名称」\n"
            "   - 音乐卡片：发送「酷狗点歌 歌曲名称 序号」\n"
            "   - MV卡片：发送「酷狗MV 歌曲名称」搜索MV，发送「酷狗MV 歌曲名称 序号」获取MV卡片\n"
            "   - 语音播放：发送「酷狗听歌 歌曲名称 序号」\n"
            "2. 网易音乐：\n"
            "   - 搜索歌单：发送「网易点歌 歌曲名称」\n"
            "   - 音乐卡片：发送「网易点歌 歌曲名称 序号」\n"
            "   - 语音播放：发送「网易听歌 歌曲名称 序号」\n"
            "3. 汽水音乐：\n"
            "   - 搜索歌单：发送「汽水点歌 歌曲名称」\n"
            "   - 音乐卡片：发送「汽水点歌 歌曲名称 序号」\n"
            "   - 语音播放：发送「汽水听歌 歌曲名称 序号」\n"
            "4. 酷我音乐：\n"
            "   - 搜索歌单：发送「酷我点歌 歌曲名称」\n"
            "   - 音乐卡片：发送「酷我点歌 歌曲名称 序号」\n"
            "   - 语音播放：发送「酷我听歌 歌曲名称 序号」\n"
            "5. QQ音乐：\n"
            "   - 搜索歌单：发送「QQ点歌 歌曲名称」\n"
            "   - 音乐卡片：发送「QQ点歌 歌曲名称 序号」\n"
            "   - 语音播放：发送「QQ听歌 歌曲名称 序号」\n"
            "6. 随机点歌：发送「随机点歌」获取随机音乐卡片\n"
            "7. 随机听歌：发送「随机听歌」获取随机语音播放\n"
            "注：序号在搜索结果中获取"
        )