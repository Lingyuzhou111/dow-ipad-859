import os
import re
import threading
import time
from asyncio import CancelledError
from concurrent.futures import Future, ThreadPoolExecutor

from bridge.context import *
from bridge.reply import *
from channel.channel import Channel
from common.dequeue import Dequeue
from common import memory
from plugins import *
from common.log import logger

try:
    from voice.audio_convert import any_to_wav
except Exception as e:
    pass

handler_pool = ThreadPoolExecutor(max_workers=8)  # 处理消息的线程池


# 抽象类, 它包含了与消息通道无关的通用处理逻辑
class ChatChannel(Channel):
    name = None  # 登录的用户名
    user_id = None  # 登录的用户id
    futures = {}  # 记录每个session_id提交到线程池的future对象, 用于重置会话时把没执行的future取消掉，正在执行的不会被取消
    sessions = {}  # 用于控制并发，每个session_id同时只能有一个context在处理
    lock = threading.Lock()  # 用于控制对sessions的访问

    def __init__(self):
        self._running = True
        _thread = threading.Thread(target=self.consume)
        _thread.setDaemon(True)
        _thread.start()
        self._thread = _thread

    # 根据消息构造context，消息内容相关的触发项写在这里
    def _compose_context(self, ctype: ContextType, content, **kwargs):
        context = Context(ctype, content)
        context.kwargs = kwargs
        if ctype == ContextType.ACCEPT_FRIEND:
            return context
        # context首次传入时，origin_ctype是None,
        # 引入的起因是：当输入语音时，会嵌套生成两个context，第一步语音转文本，第二步通过文本生成文字回复。
        # origin_ctype用于第二步文本回复时，判断是否需要匹配前缀，如果是私聊的语音，就不需要匹配前缀
        if "origin_ctype" not in context:
            context["origin_ctype"] = ctype
        # context首次传入时，receiver是None，根据类型设置receiver
        first_in = "receiver" not in context
        # 群名匹配过程，设置session_id和receiver
        if first_in:  # context首次传入时，receiver是None，根据类型设置receiver
            config = conf()
            cmsg = context["msg"]
            user_data = conf().get_user_data(cmsg.from_user_id)
            context["openai_api_key"] = user_data.get("openai_api_key")
            context["gpt_model"] = user_data.get("gpt_model")
            if context.get("isgroup", False):
                group_name = cmsg.other_user_nickname
                group_id = cmsg.other_user_id
                context["group_name"] = group_name

                group_name_white_list = config.get("group_name_white_list", [])
                group_name_keyword_white_list = config.get("group_name_keyword_white_list", [])
                if any(
                        [
                            group_name in group_name_white_list,
                            "ALL_GROUP" in group_name_white_list,
                            check_contain(group_name, group_name_keyword_white_list),
                        ]
                ):
                    group_chat_in_one_session = conf().get("group_chat_in_one_session", [])
                    session_id = f"{cmsg.actual_user_id}@@{group_id}" # 当群聊未共享session时，session_id为user_id与group_id的组合，用于区分不同群聊以及单聊
                    context["is_shared_session_group"] = False  # 默认为非共享会话群
                    if any(
                            [
                                group_name in group_chat_in_one_session,
                                "ALL_GROUP" in group_chat_in_one_session,
                            ]
                    ):
                        session_id = group_id
                        context["is_shared_session_group"] = True  # 如果是共享会话群，设置为True
                else:
                    logger.debug(f"No need reply, groupName not in whitelist, group_name={group_name}")
                    return None
                context["session_id"] = session_id
                context["receiver"] = group_id
            else:
                context["session_id"] = cmsg.other_user_id
                context["receiver"] = cmsg.other_user_id
            e_context = PluginManager().emit_event(EventContext(Event.ON_RECEIVE_MESSAGE, {"channel": self, "context": context}))
            context = e_context["context"]
            if e_context.is_pass() or context is None:
                return context
            if cmsg.from_user_id == self.user_id and not config.get("trigger_by_self", True):
                logger.debug("[chat_channel]self message skipped")
                return None

        # 消息内容匹配过程，并处理content
        if ctype == ContextType.TEXT:
            nick_name_black_list = conf().get("nick_name_black_list", [])
            if context.get("isgroup", False):  # 群聊
                # 校验关键字
                match_prefix = check_prefix(content, conf().get("group_chat_prefix"))
                match_contain = check_contain(content, conf().get("group_chat_keyword"))
                flag = False
                if context["msg"].to_user_id != context["msg"].actual_user_id:
                    if match_prefix is not None or match_contain is not None:
                        flag = True
                        if match_prefix:
                            content = content.replace(match_prefix, "", 1).strip()
                    if context["msg"].is_at:
                        nick_name = context["msg"].actual_user_nickname
                        if nick_name and nick_name in nick_name_black_list:
                            # 黑名单过滤
                            logger.warning(f"[chat_channel] Nickname {nick_name} in In BlackList, ignore")
                            return None

                        logger.info("[chat_channel]receive group at")
                        if not conf().get("group_at_off", False):
                            flag = True
                        self.name = self.name if self.name is not None else ""  # 部分渠道self.name可能没有赋值
                        pattern = f"@{re.escape(self.name)}(\u2005|\u0020)"
                        subtract_res = re.sub(pattern, r"", content)
                        if isinstance(context["msg"].at_list, list):
                            for at in context["msg"].at_list:
                                pattern = f"@{re.escape(at)}(\u2005|\u0020)"
                                subtract_res = re.sub(pattern, r"", subtract_res)
                        if subtract_res == content and context["msg"].self_display_name:
                            # 前缀移除后没有变化，使用群昵称再次移除
                            pattern = f"@{re.escape(context['msg'].self_display_name)}(\u2005|\u0020)"
                            subtract_res = re.sub(pattern, r"", content)
                        content = subtract_res
                if not flag:
                    if context["origin_ctype"] == ContextType.VOICE:
                        logger.info("[chat_channel]receive group voice, but checkprefix didn't match")
                    return None
            else:  # 单聊
                nick_name = context["msg"].from_user_nickname
                if nick_name and nick_name in nick_name_black_list:
                    # 黑名单过滤
                    logger.warning(f"[chat_channel] Nickname '{nick_name}' in In BlackList, ignore")
                    return None

                match_prefix = check_prefix(content, conf().get("single_chat_prefix", [""]))
                if match_prefix is not None:  # 判断如果匹配到自定义前缀，则返回过滤掉前缀+空格后的内容
                    content = content.replace(match_prefix, "", 1).strip()
                elif self.channel_type == 'wechatcom_app':
                    # todo:企业微信自建应用不需要前导字符
                    pass
                elif context["origin_ctype"] == ContextType.VOICE:  # 如果源消息是私聊的语音消息，允许不匹配前缀，放宽条件
                    pass
                else:
                    return None
            content = content.strip()
            img_match_prefix = check_prefix(content, conf().get("image_create_prefix",[""]))
            if img_match_prefix:
                content = content.replace(img_match_prefix, "", 1)
                context.type = ContextType.IMAGE_CREATE
            else:
                context.type = ContextType.TEXT
            context.content = content.strip()
            if "desire_rtype" not in context and conf().get(
                    "always_reply_voice") and ReplyType.VOICE not in self.NOT_SUPPORT_REPLYTYPE:
                context["desire_rtype"] = ReplyType.VOICE
        elif context.type == ContextType.VOICE:
            if "desire_rtype" not in context and conf().get(
                    "voice_reply_voice") and ReplyType.VOICE not in self.NOT_SUPPORT_REPLYTYPE:
                context["desire_rtype"] = ReplyType.VOICE
        return context

    def _handle(self, context: Context):
        if context is None or not context.content:
            return

        # 创建上下文的深拷贝，确保完全独立
        # 由于Context对象没有copy方法，我们需要手动创建一个新的Context对象
        independent_context = Context(
            type=context.type,
            content=context.content,
            kwargs={}  # 创建空字典，然后手动复制
        )

        # 手动复制 kwargs 字典中的内容
        for key in context.kwargs:
            # 对于复杂对象，创建深拷贝
            if isinstance(context.kwargs[key], dict):
                independent_context.kwargs[key] = context.kwargs[key].copy()
            elif isinstance(context.kwargs[key], list):
                independent_context.kwargs[key] = context.kwargs[key].copy()
            else:
                independent_context.kwargs[key] = context.kwargs[key]

        # 检查是否为冗长的系统配置消息，如果是则简化处理
        is_long_system_msg = (
            independent_context.type == ContextType.UNKNOWN and 
            isinstance(independent_context.content, str) and 
            len(independent_context.content) > 1000 and  # 只处理超长消息
            (independent_context.content.startswith('<sysmsg type="dynacfg">') or 
             independent_context.content.startswith('<sysmsg type="functionmsg">'))
        )
        
        if is_long_system_msg:
            # 对于冗长的系统配置消息，只记录简化的日志
            logger.debug("[chat_channel] 收到冗长系统配置消息，已忽略处理")
            return
        
        # 记录上下文信息，确保使用的是正确的上下文对象
        logger.debug("[chat_channel] ready to handle context: {}".format(independent_context))

        # 记录关键信息，用于调试
        session_id = independent_context.get("session_id", "unknown")
        receiver = independent_context.get("receiver", "unknown")
        is_group = independent_context.get("isgroup", False)
        logger.debug(f"[chat_channel] Processing message - session_id: {session_id}, receiver: {receiver}, isgroup: {is_group}")
        
        # reply的构建步骤
        reply = self._generate_reply(independent_context)

        logger.debug("[chat_channel] ready to decorate reply: {}".format(reply))

        # reply的包装步骤
        if reply and reply.content:
            reply = self._decorate_reply(independent_context, reply)

            # reply的发送步骤
            self._send_reply(independent_context, reply)

    def _generate_reply(self, context: Context, reply: Reply = Reply()) -> Reply:
        # 确保上下文中包含 isgroup 键
        if "isgroup" not in context:
            context["isgroup"] = False
            
        e_context = PluginManager().emit_event(
            EventContext(
                Event.ON_HANDLE_CONTEXT,
                {"channel": self, "context": context, "reply": reply},
            )
        )
        reply = e_context["reply"]
        if not e_context.is_pass():
            # 对于冗长的系统配置消息，简化DEBUG日志输出
            if (context.type == ContextType.UNKNOWN and 
                isinstance(context.content, str) and 
                len(context.content) > 1000 and
                (context.content.startswith('<sysmsg type="dynacfg">') or 
                 context.content.startswith('<sysmsg type="functionmsg">'))):
                logger.debug("[chat_channel] 处理冗长系统配置消息: type={}".format(context.type))
            else:
                logger.debug("[chat_channel] ready to handle context: type={}, content={}".format(context.type, context.content))
            
            if context.type == ContextType.TEXT or context.type == ContextType.IMAGE_CREATE:  # 文字和图片消息
                # 备份原始通道和接收者信息
                original_channel = context.get("original_channel")
                original_receiver = context.get("original_receiver")
                
                # 更新当前通道
                context["channel"] = e_context["channel"]
                
                # 确保不丢失原始通道和接收者信息
                if original_channel and "original_channel" not in context:
                    context["original_channel"] = original_channel
                if original_receiver and "original_receiver" not in context:
                    context["original_receiver"] = original_receiver
                    
                reply = super().build_reply_content(context.content, context)
            elif context.type == ContextType.VOICE:  # 语音消息
                cmsg = context["msg"]
                cmsg.prepare()
                file_path = context.content
                wav_path = os.path.splitext(file_path)[0] + ".wav"
                try:
                    any_to_wav(file_path, wav_path)
                except Exception as e:  # 转换失败，直接使用mp3，对于某些api，mp3也可以识别
                    logger.warning("[chat_channel]any to wav error, use raw path. " + str(e))
                    wav_path = file_path
                # 语音识别
                reply = super().build_voice_to_text(wav_path)
                # 删除临时文件
                try:
                    os.remove(file_path)
                    if wav_path != file_path:
                        os.remove(wav_path)
                except Exception as e:
                    pass
                    # logger.warning("[chat_channel]delete temp file error: " + str(e))

                if reply.type == ReplyType.TEXT:
                    new_context = self._compose_context(ContextType.TEXT, reply.content, **context.kwargs)
                    if new_context:
                        reply = self._generate_reply(new_context)
                    else:
                        return
            elif context.type == ContextType.IMAGE:  # 图片消息，当前仅做下载保存到本地的逻辑
                memory.USER_IMAGE_CACHE[context["session_id"]] = {
                    "path": context.content,
                    "msg": context.get("msg")
                }
            elif context.type == ContextType.ACCEPT_FRIEND:  # 好友申请，匹配字符串
                reply = self._build_friend_request_reply(context)
            elif context.type == ContextType.XML:
                logger.debug(f"[chat_channel] Received XML context. Content snippet: {str(context.content)[:100]}")
                cmsg = context.kwargs.get('msg')
                if cmsg and getattr(cmsg, 'is_processed_text_quote', False):
                    logger.info("[chat_channel] XML context is a processed text quote, converting to TEXT context.")
                    new_context = self._compose_context(ContextType.TEXT, cmsg.content, **context.kwargs)
                    if new_context:
                        if hasattr(context, 'is_break') and context.is_break:
                            new_context.is_break = True
                        return self._generate_reply(new_context) 
                    else:
                        logger.error("[chat_channel] Failed to convert processed XML quote to TEXT context. Original XML content remains.")
                        pass 
                else:
                    logger.debug("[chat_channel] XML message is not a processed text quote or cmsg not found. Passing.")
                    pass 
            elif context.type == ContextType.SHARING:  # 分享信息，当前无默认逻辑
                pass
            elif context.type == ContextType.FUNCTION or context.type == ContextType.FILE:  # 文件消息及函数调用等，当前无默认逻辑
                pass
            else:
                logger.warning("[chat_channel] unknown context type: {}".format(context.type))
                return
        return reply

    def _decorate_reply(self, context: Context, reply: Reply) -> Reply:
        if reply and reply.type:
            e_context = PluginManager().emit_event(
                EventContext(
                    Event.ON_DECORATE_REPLY,
                    {"channel": self, "context": context, "reply": reply},
                )
            )
            reply = e_context["reply"]
            desire_rtype = context.get("desire_rtype")
            if not e_context.is_pass() and reply and reply.type:
                if reply.type in self.NOT_SUPPORT_REPLYTYPE:
                    logger.error("[chat_channel]reply type not support: " + str(reply.type))
                    reply.type = ReplyType.ERROR
                    reply.content = "不支持发送的消息类型: " + str(reply.type)
                    return reply

                if reply.type == ReplyType.TEXT:
                    reply_text = reply.content
                    if desire_rtype == ReplyType.VOICE and ReplyType.VOICE not in self.NOT_SUPPORT_REPLYTYPE:
                        reply = super().build_text_to_voice(reply.content)
                        return self._decorate_reply(context, reply)

                    raw_parts = reply_text.split("/$")
                    segments_to_process = [p.strip() for p in raw_parts if p.strip()]

                    if not segments_to_process:
                        reply.content = ""
                    else:
                        decorated_segments = []
                        for i, segment_content in enumerate(segments_to_process):
                            current_segment_for_decoration = segment_content

                            if context.get("isgroup", False):
                                decorated_segment_payload = conf().get("group_chat_reply_prefix", "") + current_segment_for_decoration + conf().get("group_chat_reply_suffix", "")
                                if i == 0 and not conf().get("no_need_at", False):
                                    decorated_segment_payload = "@" + context["msg"].actual_user_nickname + "\n" + decorated_segment_payload
                            else:
                                decorated_segment_payload = conf().get("single_chat_reply_prefix", "") + current_segment_for_decoration + conf().get("single_chat_reply_suffix", "")
                            decorated_segments.append(decorated_segment_payload)
                        reply.content = "/$".join(decorated_segments)

                elif reply.type == ReplyType.ERROR or reply.type == ReplyType.INFO:
                    reply.content = "[" + str(reply.type) + "]\n" + reply.content
                elif reply.type == ReplyType.IMAGE_URL or reply.type == ReplyType.VOICE or reply.type == ReplyType.IMAGE or reply.type == ReplyType.FILE or reply.type == ReplyType.VIDEO or reply.type == ReplyType.VIDEO_URL or reply.type == ReplyType.APP:
                    pass
                elif reply.type == ReplyType.ACCEPT_FRIEND:
                    pass
                else:
                    logger.error("[chat_channel] unknown reply type: {}".format(reply.type))
                    return reply
            
            if desire_rtype and desire_rtype != reply.type and reply.type not in [ReplyType.ERROR, ReplyType.INFO]:
                logger.warning("[chat_channel] desire_rtype: {}, but reply type: {}".format(context.get("desire_rtype"), reply.type))
            return reply

    def _send_reply(self, context: Context, reply: Reply):
        if reply and reply.type:
            e_context = PluginManager().emit_event(
                EventContext(
                    Event.ON_SEND_REPLY,
                    {"channel": self, "context": context, "reply": reply},
                )
            )
            reply = e_context["reply"]
            if not e_context.is_pass() and reply and reply.type:
                if not reply.content and reply.type == ReplyType.TEXT: 
                    logger.debug("[chat_channel] Text reply content is empty after decoration, skipping send.")
                    return

                logger.debug("[chat_channel] ready to send reply: {}, context: {}".format(reply, context))
                if reply.type == ReplyType.TEXT and "/$" in reply.content:
                    all_segments = reply.content.split("/$")
                    segments_to_send = [s for s in all_segments if s.strip()]

                    if not segments_to_send:
                        logger.debug("[chat_channel] All segments are empty after splitting by /$, skipping send.")
                        return

                    for i, segment_text in enumerate(segments_to_send):
                        segment_reply = Reply(ReplyType.TEXT, segment_text)
                        self._send(segment_reply, context)
                        if i < len(segments_to_send) - 1:
                            time.sleep(0.3)
                else:
                    self._send(reply, context)

    def _send(self, reply: Reply, context: Context, retry_cnt=0):
        try:
            # 1. 最优先使用context中保存的原始通道信息
            if "original_channel" in context and context["original_channel"]:
                original_channel = context["original_channel"]
                logger.debug(f"[chat_channel] 使用保存的原始通道 {original_channel.__class__.__name__} 发送回复")
                
                # 确保使用原始接收者信息
                if "original_receiver" in context:
                    logger.debug(f"[chat_channel] 使用原始接收者: {context['original_receiver']}")
                
                original_channel.send(reply, context)
                
            # 2. 其次尝试使用context.channel
            elif hasattr(context, 'channel') and context.channel:
                # 使用接收消息时的原始通道发送回复
                logger.debug(f"[chat_channel] 使用context.channel原始通道 {context.channel.__class__.__name__} 发送回复")
                context.channel.send(reply, context)
            else:
                # 如果没有原始通道，才使用当前通道
                logger.debug(f"[chat_channel] 无原始通道，使用当前通道 {self.__class__.__name__} 发送回复")
                self.send(reply, context)
        except Exception as e:
            logger.error("[chat_channel] sendMsg error: {}".format(str(e)))
            if isinstance(e, NotImplementedError):
                return
            logger.exception(e)
            if retry_cnt < 2:
                time.sleep(3 + 3 * retry_cnt)
                self._send(reply, context, retry_cnt + 1)

    # 处理好友申请
    def _build_friend_request_reply(self, context):
        if isinstance(context.content, dict) and "Content" in context.content:
            logger.info("friend request content: {}".format(context.content["Content"]))
            if context.content["Content"] in conf().get("accept_friend_commands", []):
                return Reply(type=ReplyType.ACCEPT_FRIEND, content=True)
            else:
                return Reply(type=ReplyType.ACCEPT_FRIEND, content=False)
        else:
            logger.error("Invalid context content: {}".format(context.content))
            return None

    def _success_callback(self, session_id, **kwargs):  # 线程正常结束时的回调函数
        logger.debug("Worker return success, session_id = {}".format(session_id))

    def _fail_callback(self, session_id, exception, **kwargs):  # 线程异常结束时的回调函数
        logger.exception("Worker return exception: {}".format(exception))

    def _thread_pool_callback(self, session_id, **kwargs):
        def func(worker: Future):
            try:
                worker_exception = worker.exception()
                if worker_exception:
                    self._fail_callback(session_id, exception=worker_exception, **kwargs)
                else:
                    self._success_callback(session_id, **kwargs)
            except CancelledError as e: # noqa E722
                logger.info("Worker cancelled, session_id = {}".format(session_id))
            except Exception as e:
                logger.exception("Worker raise exception: {}".format(e))
            
            # Ensure semaphore release is robust and handles cases where session might be gone
            with self.lock:
                if session_id in self.sessions and self.sessions[session_id] and len(self.sessions[session_id]) > 1:
                    try:
                        self.sessions[session_id][1].release()
                        logger.debug(f"[chat_channel] Semaphore released in callback for session {session_id}")
                    except ValueError as ve: 
                        logger.error(f"[chat_channel] Semaphore for session {session_id} likely released too many times in callback. Error: {ve}")
                    except Exception as e:
                        logger.error(f"[chat_channel] Error releasing semaphore in callback for session {session_id}: {e}")
                else:
                    logger.warning(f"[chat_channel] Session {session_id} or its semaphore no longer exists in _thread_pool_callback. Cannot release.")
        return func

    def produce(self, context: Context):
        # 备份原始通道信息，确保后续处理过程中不会丢失
        if hasattr(context, 'channel') and context.channel:
            original_channel = context.channel
            if "original_channel" not in context:
                context["original_channel"] = original_channel
            logger.debug(f"[chat_channel] 保存原始通道信息: {original_channel.__class__.__name__}")
                
        # 备份原始接收者信息，确保后续处理过程中不会丢失
        if "receiver" in context and "original_receiver" not in context:
            context["original_receiver"] = context["receiver"]
            logger.debug(f"[chat_channel] 保存原始接收者信息: {context['original_receiver']}")
            
        session_id = context.get("session_id", 0)
        with self.lock:
            if session_id not in self.sessions:
                self.sessions[session_id] = [
                    Dequeue(),
                    threading.BoundedSemaphore(conf().get("concurrency_in_session", 4)),
                ]
            if context.type == ContextType.TEXT and context.content.startswith("#"):
                self.sessions[session_id][0].putleft(context)  # 优先处理管理命令
            else:
                self.sessions[session_id][0].put(context)

    # 消费者函数，单独线程，用于从消息队列中取出消息并处理
    def consume(self):
        while self._running:
            with self.lock:
                if not self._running:
                    break
                session_ids = list(self.sessions.keys())
            
            # 在处理每个session之前检查运行状态
            if not self._running:
                break
                
            for session_id in session_ids:
                if not self._running:
                    break 
                with self.lock:
                    if session_id not in self.sessions:
                        continue
                    context_queue, semaphore = self.sessions[session_id]
                
                if context_queue.empty():
                    if self._running:
                        with self.lock:
                            if session_id in self.futures and not self.futures.get(session_id):
                                logger.debug(f"[chat_channel] Deleting empty session {session_id} (pre-semaphore acquire check due to empty queue)")
                                del self.sessions[session_id]
                                if session_id in self.futures and not self.futures[session_id]:
                                    del self.futures[session_id]
                    continue

                acquired_semaphore = False
                task_submitted_and_callback_attached = False
                try:
                    if semaphore.acquire(blocking=False):
                        acquired_semaphore = True
                        if not context_queue.empty():
                            # 在提交任务前再次检查运行状态
                            if not self._running:
                                break 
                            context = context_queue.get()
                            logger.debug("[chat_channel] consume context: {}".format(context))
                            try:
                                future: Future = handler_pool.submit(self._handle, context)
                                future.add_done_callback(self._thread_pool_callback(session_id, context=context))
                                task_submitted_and_callback_attached = True
                                with self.lock:
                                    if session_id not in self.futures:
                                        self.futures[session_id] = []
                                    self.futures[session_id].append(future)
                            except RuntimeError as e:
                                if "cannot schedule new futures after shutdown" in str(e) or "cannot schedule new futures after interpreter shutdown" in str(e):
                                    logger.warning(f"[chat_channel] 线程池已关闭，程序正在停止，无法处理新消息。Session ID: {session_id}. Error: {e}")
                                    self._running = False
                                    # 设置标记以确保finally块释放信号量
                                    task_submitted_and_callback_attached = False
                                    break  # 跳出当前循环
                                else:
                                    logger.error(f"[chat_channel] RuntimeError in consume: {e}. Session ID: {session_id}")
                                    # 设置标记以确保finally块释放信号量
                                    task_submitted_and_callback_attached = False
                            except Exception as e:
                                logger.error(f"[chat_channel] Exception submitting task to handler_pool: {e}. Session ID: {session_id}")
                                # 设置标记以确保finally块释放信号量
                                task_submitted_and_callback_attached = False
                        
                        elif semaphore._initial_value == semaphore._value + 1: 
                            if self._running:
                                with self.lock:
                                    if session_id in self.futures:
                                        self.futures[session_id] = [t for t in self.futures[session_id] if not t.done()]
                                        if not self.futures[session_id]:
                                            del self.futures[session_id]
                                    
                                    if context_queue.empty() and (session_id not in self.futures or not self.futures[session_id]):
                                        logger.debug(f"[chat_channel] Deleting empty session {session_id}")
                                        del self.sessions[session_id]
                                        if session_id in self.futures and not self.futures[session_id]:
                                            del self.futures[session_id]
                        # else: semaphore acquired, but queue was empty and session not deleted. 
                        # task_submitted_and_callback_attached is False. Finally block should release.
                finally:
                    if acquired_semaphore and not task_submitted_and_callback_attached:
                        try:
                            semaphore.release()
                            logger.debug(f"[chat_channel] Semaphore released in consume finally for session {session_id} (task not submitted or submission failed)")
                        except ValueError as ve:
                             logger.error(f"[chat_channel] Error releasing semaphore in consume finally for session {session_id}. Error: {ve}")
                        except Exception as e:
                            logger.error(f"[chat_channel] Generic error releasing semaphore in consume finally for session {session_id}: {e}")

                if not self._running:
                    break
            
            if not self._running:
                break
            time.sleep(0.2)
        logger.info("[chat_channel] Consume thread gracefully finished.")

    # 取消session_id对应的所有任务，只能取消排队的消息和已提交线程池但未执行的任务
    def cancel_session(self, session_id):
        with self.lock:
            if session_id in self.sessions:
                for future in self.futures[session_id]:
                    future.cancel()
                cnt = self.sessions[session_id][0].qsize()
                if cnt > 0:
                    logger.info("Cancel {} messages in session {}".format(cnt, session_id))
                self.sessions[session_id][0] = Dequeue()

    def cancel_all_session(self):
        with self.lock:
            for session_id in self.sessions:
                if session_id in self.futures:
                    for future in self.futures[session_id]:
                        future.cancel()
                cnt = self.sessions[session_id][0].qsize()
                if cnt > 0:
                    logger.info("Cancel {} messages in session {}".format(cnt, session_id))
                self.sessions[session_id][0] = Dequeue()

    def shutdown(self):
        logger.info("[chat_channel] Shutdown called. Signaling consume thread to stop.")
        self._running = False
        
        # 取消所有pending的任务
        logger.info("[chat_channel] Cancelling all pending tasks...")
        self.cancel_all_session()
        
        # 等待消费线程结束
        if hasattr(self, '_thread') and self._thread.is_alive():
            logger.debug("[chat_channel] Waiting for consume thread to join...")
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.warning("[chat_channel] Consume thread did not stop in 5 seconds.")
            else:
                logger.info("[chat_channel] Consume thread joined successfully.")
        
        # 关闭线程池（如果它还没有被关闭）
        try:
            if hasattr(handler_pool, '_shutdown') and not handler_pool._shutdown:
                logger.info("[chat_channel] Shutting down handler_pool...")
                handler_pool.shutdown(wait=False)  # 不等待所有任务完成
        except Exception as e:
            logger.warning(f"[chat_channel] Error shutting down handler_pool: {e}")
        
        logger.info("[chat_channel] Shutdown completed.")


def check_prefix(content, prefix_list):
    if not prefix_list:
        return None
    for prefix in prefix_list:
        if content.startswith(prefix):
            return prefix
    return None


def check_contain(content, keyword_list):
    if not keyword_list:
        return None
    for ky in keyword_list:
        if content.find(ky) != -1:
            return True
    return None