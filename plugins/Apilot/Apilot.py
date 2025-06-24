import plugins
import requests
import re
import json
from urllib.parse import urlparse
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel import channel
from common.log import logger
from plugins import *
from datetime import datetime, timedelta
from PIL import Image
from io import BytesIO
BASE_URL_VVHAN = "https://api.vvhan.com/api/"
BASE_URL_ALAPI= "https://v3.alapi.cn/api/"


@plugins.register(
    name="Apilot",
    desire_priority=88,
    hidden=False,
    desc="A plugin to handle specific keywords",
    version="0.2",
    author="vision",
)
class Apilot(Plugin):
    def __init__(self):
        super().__init__()
        try:
            self.conf = super().load_config()
            self.condition_2_and_3_cities = None  # 天气查询，存储重复城市信息，Initially set to None
            if not self.conf:
                logger.warn("[Apilot] inited but no config file found or config is empty")
                self.alapi_token = None
                self.morning_news_text_enabled = False
                self.ssl_verify = True # Default to True if no config
            else:
                logger.info("[Apilot] inited and config loaded")
                self.alapi_token = self.conf.get("alapi_token")
                self.morning_news_text_enabled = self.conf.get("morning_news_text_enabled", False)
                self.ssl_verify = self.conf.get("ssl_verify", True) # Read from config, default to True
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        except Exception as e:
            raise self.handle_error(e, "[Apiot] init failed, ignore ")

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type not in [
            ContextType.TEXT
        ]:
            return
        content = e_context["context"].content.strip()
        logger.debug("[Apilot] on_handle_context. content: %s" % content)

        if content == "早报":
            reply = self.get_morning_news(self.alapi_token, self.morning_news_text_enabled)
            if reply: # get_morning_news now directly returns a Reply object
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            return # Ensure we return here whether reply is valid or not, to stop further processing
        if content == "摸鱼":
            moyu = self.get_moyu_calendar()
            reply_type = ReplyType.IMAGE_URL if self.is_valid_url(moyu) else ReplyType.TEXT
            reply = self.create_reply(reply_type, moyu)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return
        if "举牌" in content:
            # 移除前后空格
            content = content.strip()
            # 如果内容以"举牌"开头
            if content.startswith("举牌"):
                # 获取举牌后面的文字，无论是否有空格
                keyword = content[2:].strip()
                if keyword:  # 如果有内容要举牌
                    moyu = self.get_jupai_pic(keyword)
                    if moyu:
                        reply_type = ReplyType.IMAGE
                        reply = self.create_reply(reply_type, moyu)
                        e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return
        if content == "摸鱼视频":
            moyu = self.get_moyu_calendar_video()
            reply_type = ReplyType.VIDEO_URL if self.is_valid_url(moyu) else ReplyType.TEXT
            reply = self.create_reply(reply_type, moyu)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        if content == "八卦":
            bagua = self.get_mx_bagua()
            reply_type = ReplyType.IMAGE_URL if self.is_valid_url(bagua) else ReplyType.TEXT
            reply = self.create_reply(reply_type, bagua)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        if content.startswith("快递"):
            # Extract the part after "快递"
            tracking_number = content[2:].strip()

            tracking_number = tracking_number.replace('：', ':')  # 替换可能出现的中文符号
            # Check if alapi_token is available before calling the function
            if not self.alapi_token:
                self.handle_error("alapi_token not configured", "快递请求失败")
                reply = self.create_reply(ReplyType.TEXT, "请先配置alapi的token")
            else:
                # Check if the tracking_number starts with "SF" for Shunfeng (顺丰) Express
                if tracking_number.startswith("SF"):
                    # Check if the user has included the last four digits of the phone number
                    if ':' not in tracking_number:
                        reply = self.create_reply(ReplyType.TEXT, "顺丰快递需要补充寄/收件人手机号后四位，格式：SF12345:0000")
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                        return  # End the function here

                # Call query_express_info function with the extracted tracking_number and the alapi_token from config
                content = self.query_express_info(self.alapi_token, tracking_number)
                reply = self.create_reply(ReplyType.TEXT, content)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        horoscope_match = re.match(r'^([\u4e00-\u9fa5]{2}座)$', content)
        if horoscope_match:
            if content in ZODIAC_MAPPING:
                zodiac_english = ZODIAC_MAPPING[content]
                content = self.get_horoscope(self.alapi_token, zodiac_english)
                reply = self.create_reply(ReplyType.TEXT, content)
            else:
                reply = self.create_reply(ReplyType.TEXT, "请重新输入星座名称")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        hot_trend_match = re.search(r'(.{1,6})热榜$', content)
        if hot_trend_match:
            hot_trends_type = hot_trend_match.group(1).strip()  # 提取匹配的组并去掉可能的空格
            content = self.get_hot_trends(hot_trends_type)
            reply = self.create_reply(ReplyType.TEXT, content)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return


        # 天气查询
        weather_match = re.match(r'^(?:(.{2,7}?)(?:市|县|区|镇)?|(\d{7,9}))(:?今天|明天|后天|7天|七天)?(?:的)?天气$', content)
        if weather_match:
            # 如果匹配成功，提取第一个捕获组
            city_or_id = weather_match.group(1) or weather_match.group(2)
            date = weather_match.group(3)
            if not self.alapi_token:
                self.handle_error("alapi_token not configured", "天气请求失败")
                reply = self.create_reply(ReplyType.TEXT, "请先配置alapi的token")
            else:
                content = self.get_weather(self.alapi_token, city_or_id, date, content)
                reply = self.create_reply(ReplyType.TEXT, content)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

    def get_help_text(self, verbose=False, **kwargs):
        short_help_text = " 发送特定指令以获取早报、热榜、查询天气、星座运势、快递信息等！"

        if not verbose:
            return short_help_text

        help_text = "📚 发送关键词获取特定信息！\n"

        # 娱乐和信息类
        help_text += "\n🎉 娱乐与资讯：\n"
        help_text += "  🌅 早报: 发送“早报”获取早报。\n"
        help_text += "  🐟 摸鱼: 发送“摸鱼”获取摸鱼人日历。\n"
        help_text += "  🔥 热榜: 发送“xx热榜”查看支持的热榜。\n"
        help_text += "  ☯️ 八卦: 发送“八卦”获取明星八卦。\n"
        help_text += "  🪧 举牌: 发送“举牌 [消息]”来生成带有指定消息的卡片图片。\n"
        # 查询类
        help_text += "\n🔍 查询工具：\n"
        help_text += "  🌦️ 天气: 发送“城市+天气”查天气，如“北京天气”。\n"
        help_text += "  📦 快递: 发送“快递+单号”查询快递状态。如“快递112345655”\n"
        help_text += "  🌌 星座: 发送星座名称查看今日运势，如“白羊座”。\n"

        return help_text
    def get_jupai_pic(self,keyword):
        if len(keyword)>=20:
            return None
        url = "https://api.suyanw.cn/api/zt.php?msg="+keyword
        try:
            # 设置请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            # 发送请求获取图片
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            # 使用PIL处理图片
            image = Image.open(BytesIO(response.content))
            
            # 创建一个新的白色背景图片
            white_bg = Image.new('RGBA', image.size, 'white')
            
            # 如果图片有alpha通道，需要特殊处理
            if image.mode == 'RGBA':
                # 将图片与白色背景合并
                white_bg.paste(image, mask=image.split()[3])  # 使用alpha通道作为mask
            else:
                white_bg.paste(image)
            
            # 转换回BytesIO对象
            output = BytesIO()
            white_bg.convert('RGB').save(output, format='PNG')
            output.seek(0)  # 重要：将指针移回开始位置
            return output
            
        except Exception as e:
            logger.error(f"获取举牌图片失败: {e}")
            return None
    def get_morning_news(self, alapi_token, morning_news_text_enabled):
        news_api_output = None
        img_url_key = 'imgUrl' # Default for VVHAN
        news_data_key = 'data'
        date_key = 'date'
        is_alapi_with_token = False

        if not alapi_token:
            # Use VVHAN (free API)
            url = BASE_URL_VVHAN + "zaobao"
            payload = {"format": "json"} # VVHAN uses GET, so this should be params
            headers = {'User-Agent': 'Mozilla/5.0'} # VVHAN might need a User-Agent
            news_api_output = self.make_request(url, method="GET", headers=headers, params=payload, verify_ssl=self.ssl_verify)
        else:
            # Use ALAPI (with token)
            is_alapi_with_token = True
            url = BASE_URL_ALAPI + "zaobao"
            data = {"token": alapi_token, "format": "json"}
            headers = {'Content-Type': "application/x-www-form-urlencoded"}
            news_api_output = self.make_request(url, method="POST", headers=headers, data=data, verify_ssl=self.ssl_verify)
            img_url_key = 'image' # ALAPI uses 'image' in data
            # news_data_key is still 'data' but structure is different

        if isinstance(news_api_output, Exception) or not news_api_output:
            return self.create_reply(ReplyType.TEXT, self.handle_error(news_api_output, "早报API请求失败"))

        try:
            actual_img_url = ""
            news_items = []
            weiyu_text = ""
            date_str = ""

            if is_alapi_with_token:
                if news_api_output.get('code') == 200:
                    api_data = news_api_output.get(news_data_key, {})
                    actual_img_url = api_data.get(img_url_key)
                    news_items = api_data.get('news', [])
                    weiyu_text = api_data.get('weiyu', "")
                    date_str = api_data.get(date_key, "")
                else:
                    return self.create_reply(ReplyType.TEXT, self.handle_error(news_api_output, "早报获取失败(ALAPI)"))
            else: # VVHAN
                if news_api_output.get('success') == True:
                    api_data = news_api_output.get(news_data_key, []) # VVHAN data is a list of news, date is separate or part of title
                    actual_img_url = news_api_output.get(img_url_key) # VVHAN imgUrl is top-level
                    # VVHAN data format: ["news1", "news2", ..., "微语 text"], date might be in news_api_output['title'] or similar
                    if isinstance(api_data, list) and len(api_data) > 1:
                        news_items = [item for item in api_data if not item.startswith("【微语】")]
                        weiyu_item = next((item for item in api_data if item.startswith("【微语】")), "")
                        weiyu_text = weiyu_item.replace("【微语】", "").strip()
                    date_str = news_api_output.get('date', news_api_output.get('title',"").split(' ')[0]) # approximate date for VVHAN
                else:
                    return self.create_reply(ReplyType.TEXT, self.handle_error(news_api_output, "早报获取失败(VVHAN)"))

            if not actual_img_url:
                 return self.create_reply(ReplyType.TEXT, "获取早报图片URL失败")

            if morning_news_text_enabled:
                formatted_news_list = [f"{idx}. {news}" for idx, news in enumerate(news_items, 1)]
                formatted_text = f"☕ {date_str} 今日早报\n" + "\n".join(formatted_news_list)
                if weiyu_text:
                    formatted_text += f"\n\n{weiyu_text}"
                formatted_text += f"\n\n图片来源：{actual_img_url}"
                return self.create_reply(ReplyType.TEXT, formatted_text)
            else:
                # Download image and return as ReplyType.IMAGE
                image_bytes = self.make_request(actual_img_url, method="GET", verify_ssl=self.ssl_verify, return_raw_content=True)
                if isinstance(image_bytes, bytes) and image_bytes:
                    return self.create_reply(ReplyType.IMAGE, image_bytes)
                else:
                    logger.error(f"早报图片下载失败: {image_bytes}")
                    # Fallback to sending URL if download fails, or send a more specific error
                    return self.create_reply(ReplyType.TEXT, f"早报图片下载失败，请稍后重试。URL: {actual_img_url}")

        except Exception as e:
            return self.create_reply(ReplyType.TEXT, self.handle_error(e, "处理早报数据时出错"))

    def get_moyu_calendar(self):
        url = BASE_URL_VVHAN + "moyu?type=json"
        payload = "format=json"
        headers = {'Content-Type': "application/x-www-form-urlencoded"}
        moyu_calendar_info = self.make_request(url, method="POST", headers=headers, data=payload)
        # 验证请求是否成功
        if isinstance(moyu_calendar_info, dict) and moyu_calendar_info.get('success', False):
            return moyu_calendar_info['url']
        else:
            url = "https://dayu.qqsuu.cn/moyuribao/apis.php?type=json" # Fallback URL
            payload = "format=json"
            headers = {'Content-Type': "application/x-www-form-urlencoded"}
            moyu_calendar_info = self.make_request(url, method="POST", headers=headers, data=payload)
            if isinstance(moyu_calendar_info, dict) and moyu_calendar_info.get('code') == 200:
                moyu_pic_url = moyu_calendar_info["data"]
                if self.is_valid_image_url(moyu_pic_url):
                    return moyu_pic_url
                else:
                    return "周末无需摸鱼，愉快玩耍吧"
            else:
                return "暂无可用“摸鱼”服务，认真上班"

    def get_moyu_calendar_video(self):
        url = "https://dayu.qqsuu.cn/moyuribaoshipin/apis.php?type=json"
        payload = "format=json"
        headers = {'Content-Type': "application/x-www-form-urlencoded"}
        moyu_calendar_info = self.make_request(url, method="POST", headers=headers, data=payload)
        logger.debug(f"[Apilot] moyu calendar video response: {moyu_calendar_info}")
        # 验证请求是否成功
        if isinstance(moyu_calendar_info, dict) and moyu_calendar_info.get('code') == 200:
            moyu_video_url = moyu_calendar_info['data']
            if self.is_valid_image_url(moyu_video_url):
                return moyu_video_url

        # 未成功请求到视频时，返回提示信息
        return "视频版没了，看看文字版吧"

    def get_horoscope(self, alapi_token, astro_sign: str, time_period: str = "today"):
        if not alapi_token:
            url = BASE_URL_VVHAN + "horoscope"
            params = {
                'type': astro_sign,
                'time': time_period
            }
            try:
                horoscope_data = self.make_request(url, "GET", params=params)
                if isinstance(horoscope_data, dict) and horoscope_data['success']:
                    data = horoscope_data['data']

                    result = (
                        f"{data['title']} ({data['time']}):\n\n"
                        f"💡【每日建议】\n宜：{data['todo']['yi']}\n忌：{data['todo']['ji']}\n\n"
                        f"📊【运势指数】\n"
                        f"总运势：{data['index']['all']}\n"
                        f"爱情：{data['index']['love']}\n"
                        f"工作：{data['index']['work']}\n"
                        f"财运：{data['index']['money']}\n"
                        f"健康：{data['index']['health']}\n\n"
                        f"🍀【幸运提示】\n数字：{data['luckynumber']}\n"
                        f"颜色：{data['luckycolor']}\n"
                        f"星座：{data['luckyconstellation']}\n\n"
                        f"✍【简评】\n{data['shortcomment']}\n\n"
                        f"📜【详细运势】\n"
                        f"总运：{data['fortunetext']['all']}\n"
                        f"爱情：{data['fortunetext']['love']}\n"
                        f"工作：{data['fortunetext']['work']}\n"
                        f"财运：{data['fortunetext']['money']}\n"
                        f"健康：{data['fortunetext']['health']}\n"
                    )

                    return result

                else:
                    return self.handle_error(horoscope_data, '星座信息获取失败，可配置"alapi token"切换至 Alapi 服务，或者稍后再试')

            except Exception as e:
                return self.handle_error(e, "出错啦，稍后再试")
        else:
            # 使用 ALAPI 的 URL 和提供的 token
            url = BASE_URL_VVHAN + "star"
            payload = f"token={alapi_token}&star={astro_sign}"
            headers = {'Content-Type': "application/x-www-form-urlencoded"}
            try:
                horoscope_data = self.make_request(url, method="POST", headers=headers, data=payload, verify_ssl=self.ssl_verify)
                if isinstance(horoscope_data, dict) and horoscope_data.get('code') == 200:
                    data = horoscope_data['data']['day']

                    # 格式化并返回 ALAPI 提供的星座信息
                    result = (
                        f"📅 日期：{data['date']}\n\n"
                        f"💡【每日建议】\n宜：{data['yi']}\n忌：{data['ji']}\n\n"
                        f"📊【运势指数】\n"
                        f"总运势：{data['all']}\n"
                        f"爱情：{data['love']}\n"
                        f"工作：{data['work']}\n"
                        f"财运：{data['money']}\n"
                        f"健康：{data['health']}\n\n"
                        f"🔔【提醒】：{data['notice']}\n\n"
                        f"🍀【幸运提示】\n数字：{data['lucky_number']}\n"
                        f"颜色：{data['lucky_color']}\n"
                        f"星座：{data['lucky_star']}\n\n"
                        f"✍【简评】\n总运：{data['all_text']}\n"
                        f"爱情：{data['love_text']}\n"
                        f"工作：{data['work_text']}\n"
                        f"财运：{data['money_text']}\n"
                        f"健康：{data['health_text']}\n"
                    )
                    return result
                else:
                    return self.handle_error(horoscope_data, "星座获取信息获取失败，请检查 token 是否有误")
            except Exception as e:
                return self.handle_error(e, "出错啦，稍后再试")

    def get_hot_trends(self, hot_trends_type):
        # 查找映射字典以获取API参数
        hot_trends_type_en = hot_trend_types.get(hot_trends_type, None)
        if hot_trends_type_en is not None:
            url = BASE_URL_VVHAN + 'hotlist/' + hot_trends_type_en
            try:
                data = self.make_request(url, "GET", params={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }, verify_ssl=self.ssl_verify)
                if isinstance(data, dict) and data.get('success', False) == True:
                    output = []
                    topics = data['data']
                    output.append(f'更新时间：{data["update_time"]}\n')
                    for i, topic in enumerate(topics[:15], 1):
                        hot = topic.get('hot', '无热度参数, 0')
                        formatted_str = f"{i}. {topic['title']} ({hot} 浏览)\nURL: {topic['url']}\n"
                        output.append(formatted_str)
                    return "\n".join(output)
                else:
                    return self.handle_error(data, "热榜获取失败，请稍后再试")
            except Exception as e:
                return self.handle_error(e, "出错啦，稍后再试")
        else:
            supported_types = "/".join(hot_trend_types.keys())
            final_output = (
                f"👉 已支持的类型有：\n\n    {supported_types}\n"
                f"\n📝 请按照以下格式发送：\n    类型+热榜  例如：微博热榜"
            )
            return final_output

    def query_express_info(self, alapi_token, tracking_number, com="", order="asc"):
        url = BASE_URL_ALAPI + "kd"
        payload = f"token={alapi_token}&number={tracking_number}&com={com}&order={order}"
        headers = {'Content-Type': "application/x-www-form-urlencoded"}

        try:
            response_json = self.make_request(url, method="POST", headers=headers, data=payload, verify_ssl=self.ssl_verify)

            if not isinstance(response_json, dict) or response_json is None:
                return f"查询失败：api响应为空"
            code = response_json.get("code", None)
            if code != 200:
                msg = response_json.get("msg", "未知错误")
                self.handle_error(msg, f"错误码{code}")
                return f"查询失败，{msg}"
            data = response_json.get("data", None)
            formatted_result = [
                f"快递编号：{data.get('nu')}",
                f"快递公司：{data.get('com')}",
                f"状态：{data.get('status_desc')}",
                "状态信息："
            ]
            for info in data.get("info"):
                time_str = info.get('time')[5:-3]
                formatted_result.append(f"{time_str} - {info.get('status_desc')}\n    {info.get('content')}")

            return "\n".join(formatted_result)

        except Exception as e:
            return self.handle_error(e, "快递查询失败")

    def get_weather(self, alapi_token, city_or_id: str, date: str, content):
        # 根据日期选择API
        if date == '今天':
            url = BASE_URL_ALAPI + 'tianqi'
            logger.info(f"[Apilot] 使用单天天气API，查询今天天气")
        elif date in ['明天', '后天', '七天', '7天', '3天']:
            url = BASE_URL_ALAPI + 'tianqi/seven'
            logger.info(f"[Apilot] 使用七天天气API，查询日期: {date}")
        else:
            url = BASE_URL_ALAPI + 'tianqi'
            logger.info(f"[Apilot] 使用单天天气API，查询日期: {date}")

        # 判断使用id还是city请求api
        if city_or_id.isnumeric():  # 判断是否为纯数字，也即是否为 city_id
            params = {
                'city_id': city_or_id,
                'token': f'{alapi_token}'
            }
        else:
            city_info = self.check_multiple_city_ids(city_or_id)
            if city_info:
                data = city_info['data']
                formatted_city_info = "\n".join(
                    [f"{idx + 1}) {entry['province']}--{entry['leader']}, ID: {entry['city_id']}"
                     for idx, entry in enumerate(data)]
                )
                return f'查询 <{city_or_id}> 具有多条数据：\n{formatted_city_info}\n请使用id查询，发送"id天气"'

            params = {
                'city': city_or_id,
                'token': f'{alapi_token}'
            }
            
        logger.info(f"[Apilot] 查询参数: city/id={city_or_id}, date={date}")
        
        try:
            weather_data = self.make_request(url, "GET", params=params, verify_ssl=self.ssl_verify)
            if isinstance(weather_data, dict) and weather_data.get('code') == 200:
                data = weather_data['data']
                if date in ['明天', '后天', '七天', '7天', '3天']:
                    formatted_output = []
                    for num, d in enumerate(data):
                        if num == 0:
                            formatted_output.append(f"🏙️ 城市: {d['city']} ({d['province']})\n")
                        # 根据不同日期选项显示相应的天气信息
                        if date == '明天' and num != 1:
                            continue
                        if date == '后天' and num != 2:
                            continue
                        if date == '3天' and num > 2:
                            continue
                        if date in ['七天', '7天'] and num > 6:
                            continue
                        basic_info = [
                            f"🕒 日期: {d['date']}",
                            f"⭐ 天气: 🌞{d['wea_day']}| 🌛{d['wea_night']}",
                            f"🌡️ 温度: 🌞{d['temp_day']}℃| 🌛{d['temp_night']}℃",
                            f"🌅 日出/日落: {d['sunrise']} / {d['sunset']}",
                        ]
                        for i in d['index']:
                            basic_info.append(f"{i['name']}: {i['level']}")
                        formatted_output.append("\n".join(basic_info) + '\n')
                    return "\n".join(formatted_output)

                # 处理今天的天气
                update_time = data['update_time']
                dt_object = datetime.strptime(update_time, "%Y-%m-%d %H:%M:%S")
                formatted_update_time = dt_object.strftime("%m-%d %H:%M")
                # Basic Info
                if not city_or_id.isnumeric() and data['city'] not in content:  # 如果返回城市信息不是所查询的城市，重新输入
                    return "输入不规范，请输<国内城市+(今天|明天|后天|3天|七天|7天)+天气>，比如 '广州天气'"
                formatted_output = []
                basic_info = (
                    f"🏙️ 城市: {data['city']} ({data['province']})\n"
                    f"🕒 更新: {formatted_update_time}\n"
                    f"🌦️ 天气: {data['weather']}\n"
                    f"🌡️ 温度: ↓{data['min_temp']}℃| 现{data['temp']}℃| ↑{data['max_temp']}℃\n"
                    f"🌬️ 风向: {data['wind']}\n"
                    f"💦 湿度: {data['humidity']}\n"
                    f"🌅 日出/日落: {data['sunrise']} / {data['sunset']}\n"
                )
                formatted_output.append(basic_info)

                # 天气指标 Weather indicators
                weather_indicators = data.get('index')
                if weather_indicators:
                    indicators_info = '⚠️ 天气指标： \n\n'
                    for weather_indicator in weather_indicators:
                        indicators_info += (
                            f"🔴 {weather_indicator['name']}:{weather_indicator['level']}\n"
                            f"🔵 {weather_indicator['content']}\n\n"
                        )
                    formatted_output.append(indicators_info)
                    
                # Clothing Index,处理部分县区穿衣指数返回null
                #chuangyi_data = data.get('index', {}).get('chuangyi', {})
                chuangyi_data = data.get('index', {})[4]
                if chuangyi_data:
                    chuangyi_level = chuangyi_data.get('level', '未知')
                    chuangyi_content = chuangyi_data.get('content', '未知')
                else:
                    chuangyi_level = '未知'
                    chuangyi_content = '未知'

                chuangyi_info = f"👚 运动指数: {chuangyi_level} - {chuangyi_content}\n"
                formatted_output.append(chuangyi_info)

                # Next 10 hours weather
                ten_hours_later = dt_object + timedelta(hours=10)
                future_weather = []
                for hour_data in data['hour']:
                    forecast_time_str = hour_data['time']
                    forecast_time = datetime.strptime(forecast_time_str, "%Y-%m-%d %H:%M:%S")
                    if dt_object < forecast_time <= ten_hours_later:
                        future_weather.append(f"     {forecast_time.hour:02d}:00 - {hour_data['wea']} - {hour_data['temp']}°C")

                future_weather_info = "⏳ 未来10小时的天气预报:\n" + "\n".join(future_weather)
                formatted_output.append(future_weather_info)

                # Alarm Info
                if data.get('alarm'):
                    alarm_info = "⚠️ 预警信息:\n"
                    for alarm in data['alarm']:
                        alarm_info += (
                            f"🔴 标题: {alarm['title']}\n"
                            f"🟠 等级: {alarm['level']}\n"
                            f"🟡 类型: {alarm['type']}\n"
                            f"🟢 提示: {alarm['tips']}\n"
                            f"🔵 内容: {alarm['content']}\n\n"
                        )
                    formatted_output.append(alarm_info)

                return "\n".join(formatted_output)
            else:
                return self.handle_error(weather_data, "获取失败，请查看服务器log")

        except Exception as e:
            return self.handle_error(e, "获取天气信息失败")

    def get_mx_bagua(self):
        url = "https://dayu.qqsuu.cn/mingxingbagua/apis.php?type=json"
        payload = "format=json"
        headers = {'Content-Type': "application/x-www-form-urlencoded"}
        bagua_info = self.make_request(url, method="POST", headers=headers, data=payload)
        # 验证请求是否成功
        if isinstance(bagua_info, dict) and bagua_info['code'] == 200:
            bagua_pic_url = bagua_info["data"]
            if self.is_valid_image_url(bagua_pic_url):
                return bagua_pic_url
            else:
                return "周末不更新，请微博吃瓜"
        else:
            logger.error(f"错误信息：{bagua_info}")
            return "暂无明星八卦，吃瓜莫急"

    def make_request(self, url, method="GET", headers=None, params=None, data=None, json_data=None, verify_ssl: bool = True, return_raw_content: bool = False):
        try:
            response = None
            if method.upper() == "GET":
                response = requests.request(method, url, headers=headers, params=params, verify=verify_ssl)
            elif method.upper() == "POST":
                response = requests.request(method, url, headers=headers, data=data, json=json_data, verify=verify_ssl)
            else:
                return {"success": False, "message": "Unsupported HTTP method"} # This path might need review if !return_raw_content
            
            response.raise_for_status() # Raise an exception for bad status codes

            if return_raw_content:
                return response.content
            else:
                return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request to {url} failed: {e}")
            return e # Or a more structured error object/None
        except Exception as e: # Catch other potential errors, e.g. json.JSONDecodeError if response isn't JSON
            logger.error(f"Error processing request to {url}: {e}")
            return e

    def create_reply(self, reply_type, content):
        reply = Reply()
        reply.type = reply_type
        reply.content = content
        return reply

    def handle_error(self, error, message):
        logger.error(f"{message}，错误信息：{error}")
        return message

    def is_valid_url(self, url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def is_valid_image_url(self, url):
        try:
            response = requests.head(url)  # Using HEAD request to check the URL header
            # If the response status code is 200, the URL exists and is reachable.
            return response.status_code == 200
        except requests.RequestException as e:
            # If there's an exception such as a timeout, connection error, etc., the URL is not valid.
            return False

    def load_city_conditions(self):
        if self.condition_2_and_3_cities is None:
            try:
                json_file_path = os.path.join(os.path.dirname(__file__), 'duplicate-citys.json')
                with open(json_file_path, 'r', encoding='utf-8') as f:
                    self.condition_2_and_3_cities = json.load(f)
            except Exception as e:
                return self.handle_error(e, "加载condition_2_and_3_cities.json失败")


    def check_multiple_city_ids(self, city):
        self.load_city_conditions()
        city_info = self.condition_2_and_3_cities.get(city, None)
        if city_info:
            return city_info
        return None


ZODIAC_MAPPING = {
        '白羊座': 'aries',
        '金牛座': 'taurus',
        '双子座': 'gemini',
        '巨蟹座': 'cancer',
        '狮子座': 'leo',
        '处女座': 'virgo',
        '天秤座': 'libra',
        '天蝎座': 'scorpio',
        '射手座': 'sagittarius',
        '摩羯座': 'capricorn',
        '水瓶座': 'aquarius',
        '双鱼座': 'pisces'
    }

hot_trend_types = {
    "微博": "wbHot",
    "虎扑": "huPu",
    "知乎": "zhihuHot",
    "知乎日报": "zhihuDay",
    "哔哩哔哩": "bili",
    "36氪": "36Ke",
    "抖音": "douyinHot",
    "IT": "itNews",
    "虎嗅": "huXiu",
    "产品经理": "woShiPm",
    "头条": "toutiao",
    "百度": "baiduRD",
    "豆瓣": "douban",
}
if __name__ =="__main__":
    jupai = Apilot()
    jupai.get_jupai_pic("踢人")