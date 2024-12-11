# coding=utf-8
"""
Author: chazzjimel
Email: chazzjimel@gmail.com
wechat：cheung-z-x

Description:

"""
import os
import json
import time
import logging
import re
import mimetypes
import shutil
import concurrent.futures
import requests
from pydub import AudioSegment
import subprocess
from moviepy import VideoFileClip
import cv2
import numpy as np

import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from plugins import *
from .module.token_manager import tokens, refresh_access_token
from .module.api_models import create_new_chat_session, stream_chat_responses
from .module.file_uploader import FileUploader
from .module.video_frame_manager import VideoFrameManager


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@plugins.register(
    name="KimiChat",
    desire_priority=1,
    hidden=True,
    desc="kimi模型对话",
    version="0.2",
    author="chazzjimel",
)
class KimiChat(Plugin):
    def __init__(self):
        super().__init__()
        try:
            # 确保 tmp 目录存在
            if not os.path.exists('tmp'):
                os.makedirs('tmp')
                logger.info("[KimiChat] 创建 tmp 目录")
            
            # 统一文件存储目录
            # 获取插件目录的绝对路径
            self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
            self.storage_dir = os.path.join(self.plugin_dir, 'storage')
            
            # 创建存储目录结构
            self.temp_dir = os.path.join(self.storage_dir, 'temp')  # 临时件目录
            self.video_dir = os.path.join(self.storage_dir, 'video')  # 视频处理目录
            self.frames_dir = os.path.join(self.video_dir, 'frames')  # 视频帧目录
            
            # 创建所需目录
            for dir_path in [self.storage_dir, self.temp_dir, self.video_dir, self.frames_dir]:
                if not os.path.exists(dir_path):
                    os.makedirs(dir_path)
                    logger.info(f"[KimiChat] 创建目录: {dir_path}")
            
            # 初始化时清理所有临时文件
            self.clean_storage()
            
            # 设置日志编码
            import sys
            if sys.stdout.encoding != 'utf-8':
                import codecs
                sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
                sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
            
            # 加载配置
            curdir = os.path.dirname(__file__)
            config_path = os.path.join(curdir, "config.json")
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                content = ''.join(char for char in content if ord(char) >= 32 or char in '\n\r\t')
                self.conf = json.loads(content)

            # 设置日志
            log_config = self.conf.get("logging", {})
            if not log_config.get("enabled", True):
                logger.disabled = True
            else:
                logger.setLevel(log_config.get("level", "INFO"))
            
            # 从配置文件加载所有设置
            tokens['refresh_token'] = self.conf["refresh_token"]
            if not tokens['access_token']:
                refresh_access_token()
            
            # 基础配置
            self.keyword = self.conf["keyword"]
            self.reset_keyword = self.conf["reset_keyword"] 
            
            # 群组配置
            self.group_names = self.conf["group_names"]
            self.auto_summary = self.conf["auto_summary"]
            self.summary_prompt = self.conf["summary_prompt"]
            self.exclude_urls = self.conf["exclude_urls"]
            
            # 文处理配置
            self.file_upload = self.conf["file_upload"]
            self.file_triggers = self.conf["file_triggers"]
            self.file_parsing_prompts = self.conf["file_parsing_prompts"]
            self.image_prompts = self.conf["image_prompts"]
            self.use_system_prompt = self.conf["use_system_prompt"]
            self.show_custom_prompt = self.conf["show_custom_prompt"]
            
            # 其他初始化
            self.waiting_files = {}
            self.chat_data = {}
            self.processed_links = {}
            self.link_cache_time = 60  # 链接缓存时间（秒）
            
            # 注册事件处理器
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            
            # 根据配置决定是否显示初始化信息
            if log_config.get("show_init_info", True):
                logger.info("[KimiChat] ---- 插件初始化信息 ----")
                logger.info(f"[KimiChat] 关键词: {self.keyword}")
                logger.info(f"[KimiChat] 群组列表: {self.group_names}")
                logger.info(f"[KimiChat] 文件触发词: {self.file_triggers}")
                logger.info("[KimiChat] 初始化完成")
            
            # 初始化视频配置
            video_config = self.conf.get("video_config", {})
            self.video_triggers = video_config.get("trigger_keywords", ["视频", "视频分析"])
            
            # 将视频触发词添加到文件触发词列表中
            self.file_triggers.extend(self.video_triggers)
            
            self.video_save_dir = os.path.join(os.path.dirname(__file__), 'video')
            if not os.path.exists(self.video_save_dir):
                os.makedirs(self.video_save_dir)
                logger.info(f"[KimiChat] 创建视频保存目录: {self.video_save_dir}")
            
            self.frame_interval = video_config.get("frame_interval", 1.0)
            self.max_frames = video_config.get("max_frames", 10)
            self.video_summary_prompt = video_config.get("summary_prompt", "")
            self.supported_video_formats = video_config.get("supported_formats", 
                [".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"])
            
        except Exception as e:
            logger.error(f"[KimiChat] 初始化失败: {str(e)}", exc_info=True)
            raise e

        # 添加会话管理相关属性
        self.chat_sessions = {}  # 格式: {session_key: {'chat_id': chat_id, 'last_active': timestamp}}

    def check_file_format(self, file_path):
        """检查文件格式是否支持"""
        if not file_path:
            return False
        
        # 获取文件扩展名
        ext = os.path.splitext(file_path)[1].lower()
        
        # 如果是视频文件,使用视频格式列表检查
        if ext in self.supported_video_formats:
            return True
        
        # 从配置文件获取支持的格式列表
        supported_formats = self.conf.get("supported_file_formats", [
            ".dot", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".ppa", ".pptx",
            ".md", ".pdf", ".txt", ".csv",
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
            ".py", ".java", ".cpp", ".c", ".h", ".hpp", ".js", ".ts", ".html", ".css",
            ".json", ".xml", ".yaml", ".yml", ".sh", ".bat",
            ".log", ".ini", ".conf", ".properties"
        ])
        
        # 检查扩展名是否在支持列表中
        is_supported = ext in supported_formats
        
        # 添加日志输出以便调试
        if not is_supported:
            logger.warning(f"[KimiChat] 文件格式检查: 扩展名={ext}, 是否支持={is_supported}")
            logger.debug(f"[KimiChat] 支持的格式列表: {supported_formats}")
        
        return is_supported

    def get_valid_file_path(self, content):
        """获取有效的文件路径"""
        # 检查文件路径
        file_paths = [
            content,  # 原始路径
            os.path.abspath(content),  # 绝对路径
            os.path.join('tmp', os.path.basename(content)),  # tmp目录
            os.path.join(os.getcwd(), 'tmp', os.path.basename(content)),  # 完整tmp目录
            os.path.join(self.temp_dir, os.path.basename(content)),  # 临时目录
            os.path.join('plugins/cow_plugin_kimichat/video', os.path.basename(content)),  # 视频目录
        ]
        
        for path in file_paths:
            logger.debug(f"[KimiChat] 尝试路径: {path}")
            if os.path.isfile(path):
                logger.debug(f"[KimiChat] 找到文件: {path}")
                return path
        
        return None

    def extract_url(self, content):
        """从内容中提取URL并格式化为Kimi所需的格式"""
        if not content:
            return None
        
        # 更精确的URL匹配模式
        url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+(?:\?[^\s<>"]*)?(?:#[^\s<>"]*)?'
        urls = re.findall(url_pattern, content)
        if urls:
            url = urls[0]
            # 检查是否是需要排除的链接
            for exclude_url in self.exclude_urls:
                if exclude_url in url:
                    logger.info(f"[KimiChat] 检测到排除链接，跳过处理: {url}")
                    return None
            
            # 处理HTML实体编码
            url = url.replace('&amp;', '&')
            
            # 添加调试日志
            logger.debug(f"[KimiChat] 获取到URL: {url}")
            
            return f'<url id="" type="url" status="" title="" wc="">{url}</url>'
        return None

    def handle_url_content(self, content, user_id, e_context):
        """统一处理URL内容的函数"""
        content = content.strip()
        custom_prompt = None
        url = None
        
        # 统一处理链接式
        if content.startswith(self.keyword):
            # k+链接 或 k+自定义提示词+链接
            content = content[len(self.keyword):].strip()
            parts = content.split('http', 1)
            if len(parts) == 2:
                custom_prompt = parts[0].strip()
                url = 'http' + parts[1].strip()
            elif content.startswith('http'):
                url = content
                custom_prompt = self.summary_prompt
        elif self.auto_summary:
            # 自动识别链接，处理特殊字符
            url_match = re.search(r'https?://[^\s<>"]+|www\.[^\s<>"]+', content)
            if url_match:
                url = url_match.group()
                # 处理 HTML 实体编码
                url = url.replace('&amp;', '&')
                custom_prompt = self.summary_prompt
        
        # 如果找到URL,处理它
        if url:
            # 检查是否是排除的URL
            if any(exclude in url for exclude in self.exclude_urls):
                return False
            
            # 格式化URL为Kimi格式
            formatted_url = f'<url id="" type="url" status="" title="" wc="">{url}</url>'
            
            # 获取或创建会话
            session_key = self.get_session_key(user_id, e_context['context'])
            if session_key in self.chat_sessions:
                chat_id = self.chat_sessions[session_key]['chat_id']
            else:
                chat_id = create_new_chat_session()
                self.chat_sessions[session_key] = {
                    'chat_id': chat_id,
                    'last_active': time.time(),
                    'use_search': True
                }
            
            logger.info(f"[KimiChat] 检测到URL,使用提示词: {custom_prompt or self.summary_prompt}")
            
            try:
                # 构造请求内容
                content = f"{custom_prompt or self.summary_prompt}\n\n{formatted_url}"
                
                # 发送请求
                rely_content = stream_chat_responses(
                    chat_id=chat_id,
                    content=content,
                    use_search=True,
                    extend={"sidebar": True},
                    kimiplus_id="kimi",
                    use_research=False,
                    use_math=False,
                    refs=[],
                    refs_file=[]
                )
                
                if rely_content:
                    tip_message = f"\n\n发送 {self.keyword}+问题 可以继续追问"
                    reply = Reply(ReplyType.TEXT, rely_content + tip_message)
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                    return True
                    
            except Exception as e:
                logger.error(f"[KimiChat] 处理URL出错: {str(e)}", exc_info=True)
                reply = Reply(ReplyType.TEXT, f"处理URL出错: {str(e)}")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return True
            
        return False

    def on_handle_context(self, e_context: EventContext):
        """处理消息上下文"""
        if not e_context['context'].content:
            return

        content = e_context['context'].content.strip()
        context_type = e_context['context'].type
        
        # 获取用户信息
        msg = e_context['context'].kwargs.get('msg')
        is_group = e_context['context'].kwargs.get('isgroup', False)
        
        # 获取正确的用户ID和群组信息
        if is_group:
            group_id = msg.other_user_id if msg else None
            real_user_id = msg.actual_user_id if msg and msg.actual_user_id else msg.from_user_id
            waiting_id = f"{group_id}_{real_user_id}"
            group_name = msg.other_user_nickname if msg else None
        else:
            real_user_id = msg.from_user_id if msg else None
            waiting_id = real_user_id
            group_name = None

        # 处理文本消息
        if context_type == ContextType.TEXT:
            content = content.strip()
            
            # 从配置获取重置关键词
            reset_keyword = self.conf.get("reset_keyword")
            if reset_keyword and content == reset_keyword:
                logger.info(f"[KimiChat] 用户 {real_user_id} 请求重置会话")
                success, reply_text = self.reset_chat(real_user_id, e_context['context'])
                reply = Reply(ReplyType.TEXT, reply_text)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return True
            
            # 检查是否是文件识别触发词
            for trigger in self.conf.get("file_triggers", []):
                if content.startswith(trigger):
                    logger.info(f"[KimiChat] 用户 {real_user_id} 触发文件识别")
                    return self.handle_file_trigger(trigger, content, real_user_id, e_context)
            
            # 处理普通文本对话
            if self.keyword == "" or content.startswith(self.keyword):
                # 检查是否包含URL
                if 'http' in content:
                    return self.handle_url_content(content, real_user_id, e_context)
                
                # 移除关键词前缀
                msg = content[len(self.keyword):].strip() if content.startswith(self.keyword) else content
                return self.handle_normal_chat(msg, real_user_id, e_context)
            
            # 处理文件上传
        elif context_type in [ContextType.FILE, ContextType.IMAGE, ContextType.VIDEO]:
            # 检查是否在等待文件状态
            waiting_id = f"{group_id}_{real_user_id}" if is_group else real_user_id
            if waiting_id not in self.waiting_files:
                logger.debug("[KimiChat] 未检测到触发词启动的文件等待状态，跳过处理")
                return False
            waiting_info = self.waiting_files.get(waiting_id)
            if not waiting_info:
                logger.debug(f"[KimiChat] 无效的 waiting_files 状态: {waiting_id}")
                return False
            if waiting_id in self.waiting_files:
                waiting_info = self.waiting_files[waiting_id]
                
                try:
                    # 准备文件
                    file_path = self.prepare_file(msg)
                    if not file_path:
                        reply = Reply(ReplyType.TEXT, "文件准备失败，请重试")
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS
                        return True

                    # 立即发送接收提示
                    processing_reply = Reply(ReplyType.TEXT, "文件接收完毕，正在处理中...")
                    e_context["channel"].send(processing_reply, e_context["context"])

                    # 处理文件
                    return self.process_file(file_path, waiting_id, e_context)
                    
                except Exception as e:
                    logger.error(f"[KimiChat] 处理文件出错: {str(e)}", exc_info=True)
                    reply = Reply(ReplyType.TEXT, f"处理文件时出错: {str(e)}")
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                    return True
                finally:
                    if waiting_info and len(waiting_info['received']) >= waiting_info['count']:
                        self.clean_waiting_files(waiting_id)
        
        # 处理共享类型息
        elif context_type == ContextType.SHARING:
            # 判断是否启用自动总结
            if not self.conf.get("auto_summary", False):
                return False
            
            # 判断是否是群聊
            if is_group:
                # 检查群组名单
                if group_name not in self.conf.get("group_names", []):
                    logger.debug(f"[KimiChat] 群组不在自动总结列表中: {group_name}")
                    return False
                
                logger.info(f"[KimiChat] 收到群聊分享链接: {content}")
                return self.handle_url_content(content, real_user_id, e_context)
            else:
                # 私聊消息，检查私聊自动总结开关
                if not self.conf.get("private_auto_summary", False):
                    logger.debug("[KimiChat] 私聊自动总结功能已关闭")
                    return False
                
                logger.info(f"[KimiChat] 收到私聊分享链接: {content}")
                return self.handle_url_content(content, real_user_id, e_context)
        
        return False

    def clean_references(self, text):
        """清理引用记"""
        if not text:
            return text
        # 移除引用标记
        text = re.sub(r'\[\^\d+\^\]', '', text)
        # 参考文献分
        text = re.sub(r'参考文献：[\s\S]*$', '', text)
        return text.strip()

    def handle_files(self, file_list, user_id, e_context):
        """处理多文件上传"""
        try:
            chat_id = create_new_chat_session()
            file_ids = []
            
            # 1. 批量上传所有件
            uploader = FileUploader()
            for file_info in file_list:
                try:
                    file_path = file_info['path']
                    file_id = uploader.upload(
                        os.path.basename(file_path),
                        file_path
                    )
                    if file_id:
                        file_ids.append(file_id)
                except Exception as e:
                    logger.error(f"[KimiChat] 文件上传失败: {str(e)}")
                    continue
            
            if not file_ids:
                raise Exception("没有文件上传成功")
                
            # 2. 等待所有文件解析完
            for _ in range(30):  # 最多等待30秒
                parse_response = requests.post(
                    "https://kimi.moonshot.cn/api/file/parse_process",
                    json={"ids": file_ids}
                )
                if all(f["status"] == "parsed" for f in parse_response.json()):
                    break
                time.sleep(1)
            
            # 3. 检查token大小
            token_response = requests.post(
                f"https://kimi.moonshot.cn/api/chat/{chat_id}/token_size",
                json={
                    "refs": file_ids,
                    "content": ""
                }
            )
            
            if token_response.json().get("over_size"):
                raise Exception("文件容过大")
            
            # 发送息
            rely_content = stream_chat_responses(
                chat_id=chat_id,
                content=self.file_parsing_prompts,
                refs=file_ids
            )
            
            if rely_content:
                tip_message = f"\n\n发送 {self.keyword}+问题 可以继续追问"
                reply = Reply(ReplyType.TEXT, rely_content + tip_message)
            else:
                reply = Reply(ReplyType.TEXT, "件分析败，请重试")
            
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            
            return True
            
        except Exception as e:
            logger.error(f"[KimiChat] 处理文件出错: {str(e)}")
            reply = Reply(ReplyType.TEXT, f"理文件时出错: {str(e)}")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return True

    def prepare_file(self, msg):
        """准备文件，确保载完成"""
        try:
            # 确保文件已下载
            if hasattr(msg, '_prepare_fn') and not msg._prepared:
                msg._prepare_fn()
                msg._prepared = True
                time.sleep(1)  # 等待文件准备完成
            
            # 获取原始文件路径
            original_path = msg.content
            if not original_path:
                logger.error("[KimiChat] 文件路径为空")
                return None
                
            # 获取有效的文件路径
            file_path = self.get_valid_file_path(original_path)
            if not file_path:
                logger.error(f"[KimiChat] 无法找到文件: {original_path}")
                return None
                
            # 生成唯一文名(使用一个时间戳)
            timestamp = int(time.time())
            filename = f"{timestamp}_{os.path.basename(file_path)}"
            temp_path = os.path.join(self.temp_dir, filename)
            
            # 如果源文件和目标文件不是同一个文件才复制
            if os.path.abspath(file_path) != os.path.abspath(temp_path):
                shutil.copy2(file_path, temp_path)
                logger.info(f"[KimiChat] 文件已复制到: {temp_path}")
            else:
                logger.info(f"[KimiChat] 文件在临时目录中: {temp_path}")
            
            return temp_path
            
        except Exception as e:
            logger.error(f"[KimiChat] 准备文件失败: {str(e)}")
            return None

    def process_file(self, file_path, user_id, e_context):
        """处理上传的文件"""
        try:
            # 获取用户等待信息
            waiting_info = self.waiting_files.get(user_id)
            if not waiting_info:
                return False
            
            # 使用统一会话
            session_key = self.get_session_key(user_id, e_context['context'])
            if session_key in self.chat_sessions:
                chat_id = self.chat_sessions[session_key]['chat_id']
            else:
                chat_id = create_new_chat_session()
                self.chat_sessions[session_key] = {
                    'chat_id': chat_id,
                    'last_active': time.time(),
                    'use_search': True
                }
            
            # 根据文件类型进行处理
            if waiting_info['type'] == 'video':
                # 视频处理
                temp_video = None
                frames = []
                manager = None
                audio_path = None
                
                try:
                    # 检查文件大小
                    file_size = os.path.getsize(file_path) / (1024 * 1024)  # 转换为MB
                    max_size = self.conf.get("video_config", {}).get("max_size", 100)  # 默认100MB
                    
                    if file_size > max_size:
                        reply = Reply(ReplyType.TEXT, f"视频文件过大，请上传小于{max_size}MB的视频")
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS
                        return True

                    # 复制视频到临时目录
                    temp_video = os.path.join(self.temp_dir, f"temp_{int(time.time())}_{os.path.basename(file_path)}")
                    shutil.copy2(file_path, temp_video)
                    logger.info(f"[KimiChat] 视频已复制到临时目录: {temp_video}")
                    
                    # 提取音频
                    audio_path = self.extract_audio(temp_video)
                    audio_text = ""
                    if audio_path:
                        # 配置获取token
                        audio_token = self.conf.get("audio_token", "")
                        if audio_token:
                            logger.info("[KimiChat] 开始音频转写...")
                            audio_text = self.transcribe_audio(audio_path, audio_token)
                            if audio_text:
                                logger.info("[KimiChat] 音频转写完成")
                            else:
                                logger.warning("[KimiChat] 音频转写失败或无容")
                        else:
                            logger.warning("[KimiChat] 未配置audio_token，跳过音频转写")
                    else:
                        logger.warning("[KimiChat] 音频提取失败或视频无音轨，继续处理视频帧")
                    
                    # 提取视频帧
                    manager = VideoFrameManager(output_dir=self.frames_dir)
                    manager.open_video(temp_video)
                    frames = manager.extract_frames(
                        interval_seconds=self.frame_interval,
                        max_frames=self.max_frames
                    )
                    
                    # 上传帧图片
                    uploader = FileUploader()
                    file_ids = []
                    
                    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                        future_to_frame = {
                            executor.submit(uploader.upload, os.path.basename(frame_path), frame_path, skip_notification=True): (i, frame_path)
                            for i, (frame_path, _) in enumerate(frames)
                        }
                        
                        ordered_results = []
                        for future in concurrent.futures.as_completed(future_to_frame):
                            frame_index, frame_path = future_to_frame[future]
                            try:
                                file_id = future.result()
                                if file_id:
                                    ordered_results.append((frame_index, file_id))
                            except Exception as e:
                                logger.warning(f"[KimiChat] 帧 {frame_index + 1} 上传失败: {str(e)}")
                        
                        ordered_results.sort(key=lambda x: x[0])
                        file_ids = [file_id for _, file_id in ordered_results]
                    
                    if not file_ids:
                        raise Exception("没有帧图片上传成功")
                    
                    # 获取视频分析示词，并加入音频转写内容
                    summary_prompt = self.conf.get("video_config", {}).get("summary_prompt", "")
                    if audio_text:
                        logger.info("[KimiChat] 添加音频转写内容到提示词")
                        summary_prompt = f"{summary_prompt}\n\n视频音频内容：{audio_text}"
                    else:
                        logger.info("[KimiChat] 无音频转写内容")
                    
                    # 发送消息
                    rely_content = stream_chat_responses(
                        chat_id=chat_id,
                        content=summary_prompt,
                        refs=file_ids,
                        use_search=True
                    )
                    
                    if rely_content:
                        tip_message = f"\n\n发送 {self.keyword}+问题 可以继续追问"
                        reply = Reply(ReplyType.TEXT, rely_content + tip_message)
                    else:
                        reply = Reply(ReplyType.TEXT, "视频分析失败，请重试")
                    
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                    return True
                    
                finally:
                    # 清理资源
                    if manager and manager.cap:
                        manager.cap.release()
                    
                    time.sleep(0.5)
                    
                    # 清理临时文件
                    cleanup_files = []
                    if temp_video:
                        cleanup_files.append(temp_video)
                    if audio_path:
                        cleanup_files.append(audio_path)
                    for frame_path, _ in frames:
                        cleanup_files.append(frame_path)
                    
                    for file_path in cleanup_files:
                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                                logger.debug(f"[KimiChat] 已删除临时文件: {file_path}")
                        except Exception as e:
                            logger.error(f"[KimiChat] 删除临时文件失败: {file_path}, 错误: {str(e)}")
                    
                    self.clean_temp_directory()
                    # 清理 waiting_files 状态
                    if user_id in self.waiting_files:
                        del self.waiting_files[user_id]
                        logger.debug(f"[KimiChat] 清理完成的 waiting_files 状态: {user_id}")
                    
            else:
                # 处理普通文件和图片
                uploader = FileUploader()
                file_id = uploader.upload(
                    os.path.basename(file_path), 
                    file_path,
                    skip_notification=True
                )
                
                if not file_id:
                    reply = Reply(ReplyType.TEXT, "文件上传失败，请重试")
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                    return True
                
                # 记录处的文���
                waiting_info['received'].append(file_id)
                waiting_info['received_files'].append(file_path)
                
                # 检查是否已收集足够的文件
                if len(waiting_info['received']) >= waiting_info['count']:
                    # 根据文件类型选择提示词
                    file_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
                    if file_type.startswith("image"):
                        prompt = waiting_info['prompt'] or self.conf.get("image_prompts")
                    else:
                        prompt = waiting_info['prompt'] or self.conf.get("file_parsing_prompts")
                    
                    # 发送消息
                    rely_content = stream_chat_responses(
                        chat_id=chat_id,
                        content=prompt,
                        refs=waiting_info['received']
                    )
                    
                    if rely_content:
                        tip_message = f"\n\n发送 {self.keyword}+问题 可以继续追问"
                        reply = Reply(ReplyType.TEXT, rely_content + tip_message)
                    else:
                        reply = Reply(ReplyType.TEXT, "文件分析失败，请重试")
                    
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                    return True
                
                # 如果还需要更多文件,返回等待提示
                remaining = waiting_info['count'] - len(waiting_info['received'])
                reply = Reply(ReplyType.TEXT, f"已接收{len(waiting_info['received'])}个文件，还需要{remaining}个文件")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return True
                
        except Exception as e:
            logger.error(f"[KimiChat] 处理文件出错: {str(e)}")
            reply = Reply(ReplyType.TEXT, f"处理文件时出错: {str(e)}")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return True

    def handle_normal_chat(self, content, user_id, e_context):
        """处理普通对话"""
        try:
            # 每次对话前清理临时文件
            self.clean_storage()
            
            # 修改: 检查是否是单字母k的情况
            if content == self.keyword:
                logger.debug("[KimiChat] 忽略单独的触发词")
                return False
            
            # 修改: 除触发词
            msg = content[len(self.keyword):].strip() if content.startswith(self.keyword) else content
            if not msg:
                logger.debug("[KimiChat] 消息内容为空")
                return False
            
            logger.info(f"[KimiChat] 收到消息: {msg}")
            
            # 获取或创建统一会话
            session_key = self.get_session_key(user_id, e_context['context'])
            if session_key in self.chat_sessions:
                chat_id = self.chat_sessions[session_key]['chat_id']
                rely_content = stream_chat_responses(chat_id, msg, use_search=True)
            else:
                chat_id = create_new_chat_session()
                rely_content = stream_chat_responses(chat_id, msg, new_chat=True)
                self.chat_sessions[session_key] = {
                    'chat_id': chat_id,
                    'last_active': time.time(),
                    'use_search': True
                }
            
            rely_content = self.clean_references(rely_content)
            if rely_content:
                tip_message = f"\n\n发送 {self.keyword}+问题 可以继续追问"
                reply = Reply(ReplyType.TEXT, rely_content + tip_message)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return True
            
        except Exception as e:
            logger.error(f"[KimiChat] 处理消息错误: {str(e)}")
            reply = Reply(ReplyType.TEXT, f"处理失败: {str(e)}")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return True

    def process_files(self, user_id, e_context):
        """处理已接收的文件"""
        try:
            files = self.waiting_files.get(user_id, [])
            if not files or len(files) < 2:  # 至少需要元数据和一个文件
                logger.error(f"[KimiChat] 用户 {user_id} 没有待处理的文件")
                return False
            
            # 获取自定义提示词和文件列表
            metadata = files[0]  # 第一个元素是元据
            custom_prompt = metadata.get("custom_prompt")
            file_list = files[1:]  # 其他元素是文件信息
            
            # 建新会话
            chat_id = create_new_chat_session()
            
            # 传文件获取回复
            for file_info in file_list:
                try:
                    if not isinstance(file_info, dict) or "path" not in file_info:
                        logger.error(f"[KimiChat] 无效的文件信息: {file_info}")
                        continue
                    
                    file_path = file_info.get("path")
                    file_type = file_info.get("type", "application/octet-stream")
                    
                    if not file_path or not os.path.exists(file_path):
                        logger.error(f"[KimiChat] 文件不存在: {file_path}")
                        continue
                    
                    # 根据文件类型选择提示词
                    if file_type.startswith("image"):
                        prompt = self.image_prompts
                    else:
                        prompt = self.file_parsing_prompts
                    
                    # 如果有定义提示词，用自定义提示词
                    if custom_prompt:
                        prompt = custom_prompt
                    
                    logger.info(f"[KimiChat] 上传文件 {file_path} 使用提示词: {prompt}")
                    
                    # 传文件
                    file_uploader = FileUploader()
                    file_id = file_uploader.upload(
                        os.path.basename(file_path), 
                        file_path,
                        skip_notification=True
                    )
                    
                    if not file_id:
                        logger.error(f"[KimiChat] 文件 {file_path} 上传失败")
                        continue
                    
                    # 发送提示词和文件ID
                    rely_content = stream_chat_responses(chat_id, prompt, file_id)
                    
                    # 清理引用记
                    rely_content = self.clean_references(rely_content)
                    
                    if rely_content:
                        # 添加提示信息
                        tip_message = f"\n\n发送 {self.keyword}+问题 可以继续追问"
                        reply = Reply(ReplyType.TEXT, rely_content + tip_message)
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS
                
                except Exception as e:
                    logger.error(f"[KimiChat] 处理文件 {file_path if 'file_path' in locals() else '未知'} 出错: {str(e)}")
                    continue
                    
            # 理临时文件和记录
            self.clean_waiting_files(user_id)
            return True
            
        except Exception as e:
            logger.error(f"[KimiChat] 处理文件出错: {str(e)}")
            self.clean_waiting_files(user_id)
            return False

    def handle_file_recognition(self, file_path, user_id, e_context, custom_prompt=None):
        """处理文件识别"""
        try:
            logger.info(f"[KimiChat] 开始处理文件: {file_path}")
            
            # 获取文件类型
            file_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
            
            # 据文件类型择示词
            if file_type.startswith("image"):
                prompt = custom_prompt or self.image_prompts
            else:
                prompt = custom_prompt or self.file_parsing_prompts
            
            logger.info(f"[KimiChat] 用提示词: {prompt}")
            
            # 创建会话
            chat_id = create_new_chat_session()
            
            # 上传文件
            file_uploader = FileUploader()
            file_id = file_uploader.upload(
                os.path.basename(file_path), 
                file_path,
                skip_notification=True
            )
            
            if not file_id:
                logger.error(f"[KimiChat] 文上传败")
                reply = Reply(ReplyType.TEXT, "文件上传失败，请重试")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return True
            
            # 发送提示词和文件ID
            rely_content = stream_chat_responses(chat_id, prompt, file_id)
            
            # 清理引用标
            rely_content = self.clean_references(rely_content)
            
            if rely_content:
                # 添加提示信息
                tip_message = f"\n\n发送 {self.keyword}+问题 可以续追问"
                reply = Reply(ReplyType.TEXT, rely_content + tip_message)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return True
                
        except Exception as e:
            logger.error(f"[KimiChat] 处理文件识别: {str(e)}")
            reply = Reply(ReplyType.TEXT, f"处理文件时出错: {str(e)}")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return True
        
        return False

    def process_waiting_files(self, user_id, e_context):
        """处理等待中的文件"""
        try:
            if user_id not in self.waiting_files:
                return False
            
            waiting_info = self.waiting_files[user_id]
            
            # 检查理否超时
            if time.time() - waiting_info['trigger_time'] > waiting_info['timeout']:
                logger.warning(f"[KimiChat] 件处理超时: {user_id}")
                self.clean_waiting_files(user_id)
                reply = Reply(ReplyType.TEXT, "文件处理超时,请新上传")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return True
            
            # 其余处理逻辑保持不变
            ...
        except Exception as e:
            logger.error(f"[KimiChat] 处理等待文件错: {str(e)}")
            self.clean_waiting_files(user_id)
            reply = Reply(ReplyType.TEXT, f"处理文件时出错: {str(e)}")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return True
        
        return False

    def clean_waiting_files(self, user_id):
        """清理用户的时文件和等待记录"""
        try:
            if user_id in self.waiting_files:
                waiting_info = self.waiting_files[user_id]
                # 清理临时件
                # 清理接收到的文件
                for file_path in waiting_info.get('received_files', []):
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            logger.debug(f"[KimiChat] 删除文件: {file_path}")
                        except Exception as e:
                            logger.error(f"[KimiChat] 删除文件失败: {file_path}, 错误: {str(e)}")

            # 删除 waiting_files 状态
            del self.waiting_files[user_id]
            logger.debug(f"[KimiChat] 已清理 waiting_files 状态: {user_id}")

        except Exception as e:
            logger.error(f"[KimiChat] 清理 waiting_files 失败: {str(e)}")
                
 

    def handle_file_trigger(self, trigger, content, user_id, e_context):
        """处理文件触发"""
        # 获取用户信息
        msg = e_context['context'].kwargs.get('msg')
        is_group = e_context["context"].kwargs.get('isgroup', False)
        
        # 获取正确的用户ID
        if is_group:
            group_id = msg.other_user_id if msg else None
            real_user_id = msg.actual_user_id if msg and msg.actual_user_id else msg.from_user_id
            waiting_id = f"{group_id}_{real_user_id}"
        else:
            real_user_id = msg.from_user_id if msg else user_id
            waiting_id = real_user_id
            
        logger.info(f"[KimiChat] 用户 {real_user_id} 触发文件处理, 触发词: {trigger}")
        
        # 如果有未完成任务,先清理掉
        if waiting_id in self.waiting_files:
            self.clean_waiting_files(waiting_id)
        
        # 解析文件数量和自定义提示词
        remaining = content[len(trigger):].strip()
        file_count = 1
        custom_prompt = None
        
        # 检查是否指定了文件数量
        match = re.match(r'(\d+)\s*(.*)', remaining)
        if match:
            file_count = int(match.group(1))
            custom_prompt = match.group(2).strip() if match.group(2) else None
        else:
            custom_prompt = remaining if remaining else None
        
        # 从配置获取最大文件数限制
        max_files = self.conf.get("max_file_size", 50)  # 默认50
        if file_count > max_files:
            reply = Reply(ReplyType.TEXT, f"最多支持同时上传{max_files}个文件")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return True
        
        # 确定文件类型
        file_type = 'file'  # 默认类型
        
        # ��配置获取视频触发词
        video_triggers = self.conf.get("video_config", {}).get("trigger_keywords", ["视频", "视频分析"])
        
        # 只需要判断是否是视频触发词
        if trigger in video_triggers:
            file_type = 'video'
        
        # 获取超时时间(分钟)
        timeout_minutes = self.conf.get("file_timeout", 300) // 60
        
        # 保存处理信息
        waiting_info = {
            'count': file_count,
            'received': [],
            'received_files': [],
            'prompt': custom_prompt,
            'trigger_time': time.time(),
            'timeout': timeout_minutes * 60,  # 转换为秒
            'trigger_user_id': real_user_id,
            'is_group': is_group,
            'group_id': msg.other_user_id if is_group else None,
            'type': file_type
        }
        
        # 保存等待状态
        self.waiting_files[waiting_id] = waiting_info
        logger.debug(f"[KimiChat] 设置等待状态: waiting_id={waiting_id}, info={waiting_info}")
        
        # 根据文件类型返回对应提示文本
        if file_type == 'video':
            reply_text = "请发送需要识别的视频"
        else:
            reply_text = f"请在{timeout_minutes}分钟内发送{file_count}个文件"
        
        reply = Reply(ReplyType.TEXT, reply_text)
        e_context["reply"] = reply
        e_context.action = EventAction.BREAK_PASS
        return True

    def get_session_key(self, user_id, context):
        """生成会话值
        群聊: 使用群ID作为key，整个群共享一个会话
        私聊: 使用用户ID为key每个用户独立会话
        """
        if context.kwargs.get('isgroup', False):
            group_id = context.kwargs['msg'].other_user_id
            return f"group_{group_id}"
        return f"private_{user_id}"

    def get_or_create_session(self, user_id, context):
        """获取或创建会话"""
        try:
            session_key = self.get_session_key(user_id, context)
            
            # 检查现有会话是否有效
            if session_key in self.chat_sessions:
                chat_info = self.chat_sessions[session_key]
                
                # 验证会话是否有
                try:
                    response = requests.post(
                        f"https://kimi.moonshot.cn/api/chat/{chat_info['chat_id']}/token_size",
                        json={"content": ""}
                    )
                    if response.status_code == 200:
                        # 会话有效,更新最后活动时间
                        chat_info['last_active'] = time.time()
                        return chat_info
                    
                except Exception as e:
                    logger.warning(f"[KimiChat] 会话 {chat_info['chat_id']} 已失效，创建会话")
            
            # 创建新会话
            chat_id = create_new_chat_session()
            session = {
                'chat_id': chat_id,
                'last_active': time.time(),
                'use_search': True
            }
            self.chat_sessions[session_key] = session
            logger.info(f"[KimiChat] 创建新会话: key={session_key}, chat_id={chat_id}")
            return session
            
        except Exception as e:
            logger.error(f"[KimiChat] 获取或会话失败: {str(e)}")
            # 新会作为后备案
            chat_id = create_new_chat_session()
            session = {
                'chat_id': chat_id,
                'last_active': time.time(),
                'use_search': True
            }
            self.chat_sessions[session_key] = session
            return session

    def reset_chat(self, user_id, context):
        """重置用户会话"""
        try:
            session_key = self.get_session_key(user_id, context)
            
            if context.kwargs.get('isgroup', False):
                reply_text = "已重置本群的对话，所有群成员将开始新的对。"
            else:
                reply_text = "已重置与您的对话，我们可以开始新的交谈。"
            
            # 清理会话数据
            if session_key in self.chat_sessions:
                del self.chat_sessions[session_key]
            
            # 清理等待中的文件数据
            self.clean_waiting_files(user_id)
            
            logger.info(f"[KimiChat] 已重置会话: {session_key}")
            
            # 添加提示信息
            reply_text += f"\n\n发送 {self.keyword}+问题 可以继续追问"
            
            return True, reply_text
        except Exception as e:
            logger.error(f"[KimiChat] 重置会话出错: {str(e)}")
            return False, "重置会话时出现错误，请稍后重试"

    def handle_message(self, context):
        group_name = context.get("group_name")
        if group_name not in self.conf.get("allowed_groups", []):
            return  # 如果不在允许的群组列表中，直接返回
        
        # 继续理其他逻辑
        ...

    def check_video_format(self, file_path):
        """检查视频格式是否持"""
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self.supported_video_formats

    def handle_video(self, video_path, user_id, e_context):
        """处理视频"""
        try:
            # 使用统一会话
            session_key = self.get_session_key(user_id, e_context['context'])
            if session_key in self.chat_sessions:
                chat_id = self.chat_sessions[session_key]['chat_id']
            else:
                chat_id = create_new_chat_session()
                self.chat_sessions[session_key] = {
                    'chat_id': chat_id,
                    'last_active': time.time(),
                    'use_search': True
                }
            
            # 其余视频处理逻辑...
            
        except Exception as e:
            logger.error(f"[KimiChat] 处理视频失败: {str(e)}")
            return False

    def handle_image(self, image_path, user_id, e_context):
        """处理片"""
        try:
            # 使用统一话
            session_key = self.get_session_key(user_id, e_context['context'])
            if session_key in self.chat_sessions:
                chat_id = self.chat_sessions[session_key]['chat_id']
            else:
                chat_id = create_new_chat_session()
                self.chat_sessions[session_key] = {
                    'chat_id': chat_id,
                    'last_active': time.time(),
                    'use_search': True
                }
            
            # 其余图片处理逻辑...
            
        except Exception as e:
            logger.error(f"[KimiChat] 处理图片出错: {str(e)}")
            return False

    def clean_storage(self, file_paths=None):
        """清理存的文件
        Args:
            file_paths: 指定要清理的文件径列表,为None时清理所有临时文件
        """
        try:
            if file_paths:
                # 清理指定文件
                for path in file_paths:
                    if path and os.path.exists(path):
                        os.remove(path)
                        logger.debug(f"[KimiChat] 已删除文件: {path}")
            else:
                # 清理所有临时文件
                for root, _, files in os.walk(self.storage_dir):
                    for file in files:
                        try:
                            file_path = os.path.join(root, file)
                            os.remove(file_path)
                            logger.debug(f"[KimiChat] 已删除文件: {file_path}")
                        except Exception as e:
                            logger.error(f"[KimiChat] 删除文件失败: {file_path}, 错误: {str(e)}")
                        
        except Exception as e:
            logger.error(f"[KimiChat] 清理存储文件出错: {str(e)}")

    def clean_temp_directory(self):
        """清理临时目录中的所有文件"""
        try:
            # 清理 temp 目录
            if os.path.exists(self.temp_dir):
                for filename in os.listdir(self.temp_dir):
                    file_path = os.path.join(self.temp_dir, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            logger.debug(f"[KimiChat] 已删除临时文件: {file_path}")
                    except Exception as e:
                        logger.error(f"[KimiChat] 删除临时文件失败: {file_path}, 错误: {str(e)}")
                    
            # 清理 frames 目录
            if os.path.exists(self.frames_dir):
                for filename in os.listdir(self.frames_dir):
                    file_path = os.path.join(self.frames_dir, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            logger.debug(f"[KimiChat] 已删除帧文件: {file_path}")
                    except Exception as e:
                        logger.error(f"[KimiChat] 删除帧文件失败: {file_path}, 错误: {str(e)}")
                    
        except Exception as e:
            logger.error(f"[KimiChat] 清理临时目录失败: {str(e)}")

    def extract_audio(self, video_path):
        """从视频中提取音频(使用moviepy)"""
        try:
            # 生成唯一的音频文名
            audio_filename = f"audio_{int(time.time())}.mp3"
            audio_path = os.path.join(self.temp_dir, audio_filename)
            
            try:
                # 使用moviepy提取频
                video = VideoFileClip(video_path)
                if video.audio:  # 确保视频有音轨
                    video.audio.write_audiofile(
                        audio_path,
                        codec='libmp3lame',
                        logger=None  # 禁进度输出
                    )
                    video.close()  # 释放资源
                    
                    if os.path.exists(audio_path):
                        logger.info(f"[KimiChat] 音频提取成功: {audio_path}")
                        return audio_path
                    else:
                        logger.error("[KimiChat] 音频文件未生成")
                        return None
                else:
                    logger.warning("[KimiChat] 视频没有音轨")
                    return None
                
            except Exception as e:
                logger.error(f"[KimiChat] moviepy处理失败: {str(e)}")
                return None
            
        except Exception as e:
            logger.error(f"[KimiChat] 提取音频失败: {str(e)}")
            return None

    def transcribe_audio(self, audio_path, token):
        """转写频为文"""
        try:
            url = "https://api.siliconflow.cn/v1/audio/transcriptions"
            
            # 准备文件和表单数据
            files = {
                'file': ('audio.mp3', open(audio_path, 'rb'), 'audio/mpeg'),
                'model': (None, 'FunAudioLLM/SenseVoiceSmall')
            }
            
            headers = {
                "Authorization": f"Bearer {token}"
            }
            
            response = requests.post(url, files=files, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            return result.get('text', '')
        except Exception as e:
            logger.error(f"[KimiChat] 音频转写失败: {str(e)}")
            return None
        finally:
            # 确保文件已关闭
            for file in files.values():
                if hasattr(file[1], 'close'):
                    file[1].close()

