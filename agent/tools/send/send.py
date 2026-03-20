# -*- coding: utf-8 -*-
"""
发送文件工具

将本地文件发送给用户：
- 支持图片、视频、音频、文档等多种类型
- 返回文件元数据供渠道发送
- 不支持URL（URL应直接包含在文本回复中）
"""

# 导入操作系统模块
import os

# 导入类型提示
from typing import Dict, Any

# 导入路径处理
from pathlib import Path

# 导入工具基类和结果类
from agent.tools.base_tool import BaseTool, ToolResult

# 导入路径扩展工具
from common.utils import expand_path


class Send(BaseTool):
    """
    发送文件工具类
    
    功能：
    - 发送本地文件给用户
    - 自动检测文件类型
    - 返回文件元数据
    
    注意：
    - 只支持本地文件路径
    - URL应直接在文本回复中包含
    """
    
    # 工具名称
    name: str = "send"
    
    # 工具描述
    description: str = "Send a LOCAL file (image, video, audio, document) to the user. Only for local file paths. Do NOT use this for URLs — URLs should be included directly in your text reply, the system will handle them automatically."
    
    # 参数JSON Schema
    params: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Local file path to send. Must be an absolute path or relative to workspace. Do NOT pass URLs here."
            },
            "message": {
                "type": "string",
                "description": "Optional message to accompany the file"
            }
        },
        "required": ["path"]
    }
    
    def __init__(self, config: dict = None):
        """
        初始化Send工具
        
        Args:
            config: 配置字典，可包含：
                - cwd: 工作目录
        """
        # 存储配置
        self.config = config or {}
        # 获取工作目录
        self.cwd = self.config.get("cwd", os.getcwd())
        
        # 支持的文件类型扩展名
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.ico'}
        self.video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v'}
        self.audio_extensions = {'.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.wma'}
        self.document_extensions = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.md'}
    
    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """
        执行文件发送操作
        
        Args:
            args: 包含文件路径和可选消息
                - path: 本地文件路径
                - message: 附加消息
            
        Returns:
            ToolResult: 文件元数据供渠道发送
        """
        # 获取参数
        path = args.get("path", "").strip()       # 文件路径
        message = args.get("message", "")          # 附加消息
        
        # 检查路径参数
        if not path:
            return ToolResult.fail("Error: path parameter is required")
        
        # 解析路径
        absolute_path = self._resolve_path(path)
        
        # 检查文件是否存在
        if not os.path.exists(absolute_path):
            return ToolResult.fail(f"Error: File not found: {path}")
        
        # 检查是否可读
        if not os.access(absolute_path, os.R_OK):
            return ToolResult.fail(f"Error: File is not readable: {path}")
        
        # 获取文件信息
        file_ext = Path(absolute_path).suffix.lower()  # 扩展名
        file_size = os.path.getsize(absolute_path)      # 文件大小
        file_name = Path(absolute_path).name            # 文件名
        
        # 确定文件类型
        if file_ext in self.image_extensions:
            file_type = "image"
            mime_type = self._get_image_mime_type(file_ext)
        elif file_ext in self.video_extensions:
            file_type = "video"
            mime_type = self._get_video_mime_type(file_ext)
        elif file_ext in self.audio_extensions:
            file_type = "audio"
            mime_type = self._get_audio_mime_type(file_ext)
        elif file_ext in self.document_extensions:
            file_type = "document"
            mime_type = self._get_document_mime_type(file_ext)
        else:
            file_type = "file"
            mime_type = "application/octet-stream"
        
        # 返回文件元数据（file_to_send）
        result = {
            "type": "file_to_send",              # 类型标识
            "file_type": file_type,              # 文件类型
            "path": absolute_path,               # 绝对路径
            "file_name": file_name,              # 文件名
            "mime_type": mime_type,              # MIME类型
            "size": file_size,                   # 文件大小
            "size_formatted": self._format_size(file_size),  # 格式化大小
            "message": message or f"正在发送 {file_name}"    # 附加消息
        }
        
        return ToolResult.success(result)
    
    def _resolve_path(self, path: str) -> str:
        """
        解析路径为绝对路径
        
        Args:
            path: 相对或绝对路径
            
        Returns:
            str: 绝对路径
        """
        # 扩展 ~ 为用户主目录
        path = expand_path(path)
        if os.path.isabs(path):
            return path
        # 相对路径基于工作目录
        return os.path.abspath(os.path.join(self.cwd, path))
    
    def _get_image_mime_type(self, ext: str) -> str:
        """
        获取图片的MIME类型
        
        Args:
            ext: 文件扩展名
            
        Returns:
            str: MIME类型
        """
        # MIME类型映射
        mime_map = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.gif': 'image/gif',
            '.webp': 'image/webp', '.bmp': 'image/bmp',
            '.svg': 'image/svg+xml', '.ico': 'image/x-icon'
        }
        return mime_map.get(ext, 'image/jpeg')
    
    def _get_video_mime_type(self, ext: str) -> str:
        """
        获取视频的MIME类型
        
        Args:
            ext: 文件扩展名
            
        Returns:
            str: MIME类型
        """
        # MIME类型映射
        mime_map = {
            '.mp4': 'video/mp4', '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime', '.mkv': 'video/x-matroska',
            '.webm': 'video/webm', '.flv': 'video/x-flv'
        }
        return mime_map.get(ext, 'video/mp4')
    
    def _get_audio_mime_type(self, ext: str) -> str:
        """
        获取音频的MIME类型
        
        Args:
            ext: 文件扩展名
            
        Returns:
            str: MIME类型
        """
        # MIME类型映射
        mime_map = {
            '.mp3': 'audio/mpeg', '.wav': 'audio/wav',
            '.ogg': 'audio/ogg', '.m4a': 'audio/mp4',
            '.flac': 'audio/flac', '.aac': 'audio/aac'
        }
        return mime_map.get(ext, 'audio/mpeg')
    
    def _get_document_mime_type(self, ext: str) -> str:
        """
        获取文档的MIME类型
        
        Args:
            ext: 文件扩展名
            
        Returns:
            str: MIME类型
        """
        # MIME类型映射
        mime_map = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.txt': 'text/plain',
            '.md': 'text/markdown'
        }
        return mime_map.get(ext, 'application/octet-stream')
    
    def _format_size(self, size_bytes: int) -> str:
        """
        格式化文件大小为人类可读格式
        
        Args:
            size_bytes: 文件大小（字节）
            
        Returns:
            str: 格式化的大小字符串
        """
        # 单位列表
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"
