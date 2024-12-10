import os
import cv2
import numpy as np
from datetime import datetime
import logging
import traceback
from typing import List, Optional, Tuple, Union
from pathlib import Path

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class VideoFrameManager:
    def __init__(self, output_dir: Optional[Union[str, Path]] = None):
        """
        初始化视频帧管理器
        Args:
            output_dir: 帧输出目录，如果为None则使用临时目录
        """
        self.output_dir = str(output_dir) if output_dir else None
        self.cap: Optional[cv2.VideoCapture] = None
        
    def open_video(self, video_path: Union[str, Path]) -> None:
        """
        打开视频文件
        Args:
            video_path: 视频文件路径
        Raises:
            Exception: 无法打开视频文件时抛出
        """
        if self.cap is not None:
            self.cap.release()
        
        try:
            self.cap = cv2.VideoCapture(str(video_path))
            if not self.cap.isOpened():
                raise Exception("无法打开视频文件")
            
            # 获取视频信息
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            if fps <= 0 or total_frames <= 0:
                raise Exception("无效的视频参数")
            
            # 验证视频是否可读
            ret, frame = self.cap.read()
            if not ret or frame is None:
                raise Exception("无法读取视频帧")
            
            # 重置视频位置
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            
            logger.info(f"[VideoFrameManager] 成功打开视频 - FPS: {fps}, 总帧数: {total_frames}")
            
        except Exception as e:
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            raise Exception(f"视频文件打开失败: {str(e)}")
        
    def extract_frames(self, interval_seconds: float = 1.0, max_frames: int = 50) -> List[Tuple[str, float]]:
        """
        提取视频帧
        Args:
            interval_seconds: 帧间隔时间(秒)
            max_frames: 最大帧数
        Returns:
            list of (frame_path, timestamp)
        Raises:
            Exception: 视频未打开或提取失败时抛出
        """
        if self.cap is None:
            raise Exception("请先打开视频文件")
            
        if self.output_dir is None:
            raise Exception("未设置输出目录")
            
        try:
            # 获取视频信息
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps
            
            logger.debug(f"视频信息 - 帧数: {total_frames}, FPS: {fps}, 时长: {duration}秒")
            
            # 对于长视频，自动调整提取策略
            if duration > 180:  # 3分钟以上的视频
                # 将视频分为几个关键时间点
                key_points = [
                    0,                  # 开始
                    duration * 0.25,    # 1/4处
                    duration * 0.5,     # 中间
                    duration * 0.75,    # 3/4处
                    duration - 1        # 结束(减1秒避免最后一帧可能的问题)
                ]
                
                frames_per_point = max_frames // len(key_points)
                interval = 1.0  # 每个关键点周围1秒的间隔
                
                frames: List[Tuple[str, float]] = []
                for point in key_points:
                    start_time = max(0, point - interval)
                    end_time = min(duration, point + interval)
                    
                    for i in range(frames_per_point):
                        timestamp = start_time + (end_time - start_time) * i / frames_per_point
                        frame_idx = int(timestamp * fps)
                        
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                        ret, frame = self.cap.read()
                        if ret:
                            frame_path = str(Path(self.output_dir) / f"{i+1}.jpg")
                            cv2.imwrite(frame_path, frame)
                            frames.append((frame_path, timestamp))
                            logger.debug(f"成功保存帧 {i+1} 到 {frame_path}")
                
                return frames
                
            else:  # 短视频使用原的均匀提取方式
                interval_frames = int(interval_seconds * fps)
                if interval_frames < 1:
                    interval_frames = 1
                
                logger.debug(f"计算的帧间隔: {interval_frames}")
                
                frames: List[Tuple[str, float]] = []
                frame_count = 0
                
                while True:
                    ret, frame = self.cap.read()
                    if not ret:
                        break
                        
                    if frame_count % interval_frames == 0:
                        frame_path = str(Path(self.output_dir) / f"{len(frames)+1}.jpg")
                        cv2.imwrite(frame_path, frame)
                        timestamp = frame_count / fps
                        frames.append((frame_path, timestamp))
                        logger.debug(f"成功保存帧 {len(frames)} 到 {frame_path}")
                        
                        if len(frames) >= max_frames:
                            break
                            
                    frame_count += 1
                
                return frames
                
        except Exception as e:
            logger.error(f"提取视频帧失败: {str(e)}")
            return []
        
    def __del__(self) -> None:
        """析构函数，确保释放资源"""
        if self.cap is not None:
            self.cap.release()
            logger.debug("视频资源已释放")
