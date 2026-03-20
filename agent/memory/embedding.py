# -*- coding: utf-8 -*-
"""
向量嵌入提供者模块

支持OpenAI和本地嵌入模型。
提供记忆系统的向量嵌入能力。
"""

# 导入哈希模块
import hashlib

# 导入抽象基类
from abc import ABC, abstractmethod

# 导入类型提示
from typing import List, Optional


class EmbeddingProvider(ABC):
    """
    嵌入提供者基类
    
    所有嵌入提供者都应继承此类。
    """

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """
        为文本生成嵌入向量
        
        Args:
            text: 输入文本
            
        Returns:
            嵌入向量（浮点数列表）
        """
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        为多个文本生成嵌入向量
        
        Args:
            texts: 文本列表
            
        Returns:
            嵌入向量列表
        """
        pass
    
    @property
    @abstractmethod
    def dimensions(self) -> int:
        """
        获取嵌入维度
        
        Returns:
            int: 向量维度
        """
        pass


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    OpenAI嵌入提供者
    
    使用REST API调用OpenAI嵌入服务。
    """
    
    def __init__(self, model: str = "text-embedding-3-small", api_key: Optional[str] = None, api_base: Optional[str] = None):
        """
        初始化OpenAI嵌入提供者
        
        Args:
            model: 模型名称（text-embedding-3-small 或 text-embedding-3-large）
            api_key: OpenAI API密钥
            api_base: 可选的API基础URL
        """
        self.model = model          # 模型名称
        self.api_key = api_key      # API密钥
        self.api_base = api_base or "https://api.openai.com/v1"  # API基础URL

        # 验证API密钥
        if not self.api_key or self.api_key in ["", "YOUR API KEY", "YOUR_API_KEY"]:
            raise ValueError("OpenAI API key is not configured. Please set 'open_ai_api_key' in config.json")

        # 根据模型设置维度
        self._dimensions = 1536 if "small" in model else 3072

    def _call_api(self, input_data):
        """
        调用OpenAI嵌入API
        
        Args:
            input_data: 输入数据（字符串或列表）
            
        Returns:
            API响应JSON
        """
        import requests

        # 构建URL
        url = f"{self.api_base}/embeddings"
        # 构建请求头
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        # 构建请求数据
        data = {
            "input": input_data,
            "model": self.model
        }

        try:
            # 发送POST请求
            response = requests.post(url, headers=headers, json=data, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError as e:
            # 连接错误
            raise ConnectionError(f"Failed to connect to OpenAI API at {url}. Please check your network connection and api_base configuration. Error: {str(e)}")
        except requests.exceptions.Timeout as e:
            # 超时错误
            raise TimeoutError(f"OpenAI API request timed out after 10s. Please check your network connection. Error: {str(e)}")
        except requests.exceptions.HTTPError as e:
            # HTTP错误
            if e.response.status_code == 401:
                raise ValueError(f"Invalid OpenAI API key. Please check your 'open_ai_api_key' in config.json")
            elif e.response.status_code == 429:
                raise ValueError(f"OpenAI API rate limit exceeded. Please try again later.")
            else:
                raise ValueError(f"OpenAI API request failed: {e.response.status_code} - {e.response.text}")

    def embed(self, text: str) -> List[float]:
        """
        为单个文本生成嵌入
        
        Args:
            text: 输入文本
            
        Returns:
            嵌入向量
        """
        result = self._call_api(text)
        return result["data"][0]["embedding"]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        为多个文本生成嵌入
        
        Args:
            texts: 文本列表
            
        Returns:
            嵌入向量列表
        """
        if not texts:
            return []

        result = self._call_api(texts)
        return [item["embedding"] for item in result["data"]]

    @property
    def dimensions(self) -> int:
        """获取嵌入维度"""
        return self._dimensions


class EmbeddingCache:
    """
    嵌入缓存
    
    缓存嵌入结果避免重复计算。
    """

    def __init__(self):
        """初始化缓存"""
        self.cache = {}

    def get(self, text: str, provider: str, model: str) -> Optional[List[float]]:
        """
        获取缓存的嵌入
        
        Args:
            text: 文本
            provider: 提供者名称
            model: 模型名称
            
        Returns:
            缓存的嵌入向量，如果没有则返回None
        """
        key = self._compute_key(text, provider, model)
        return self.cache.get(key)
    
    def put(self, text: str, provider: str, model: str, embedding: List[float]):
        """
        缓存嵌入
        
        Args:
            text: 文本
            provider: 提供者名称
            model: 模型名称
            embedding: 嵌入向量
        """
        key = self._compute_key(text, provider, model)
        self.cache[key] = embedding
    
    @staticmethod
    def _compute_key(text: str, provider: str, model: str) -> str:
        """
        计算缓存键
        
        Args:
            text: 文本
            provider: 提供者
            model: 模型
            
        Returns:
            MD5哈希键
        """
        content = f"{provider}:{model}:{text}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()


def create_embedding_provider(
    provider: str = "openai",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None
) -> EmbeddingProvider:
    """
    创建嵌入提供者的工厂函数

    支持 "openai" 和 "linkai" 提供者（都使用OpenAI兼容的REST API）。
    如果初始化失败，调用者应回退到仅关键词搜索。

    Args:
        provider: 提供者名称（"openai" 或 "linkai"）
        model: 模型名称（默认：text-embedding-3-small）
        api_key: API密钥（必需）
        api_base: API基础URL
        
    Returns:
        EmbeddingProvider实例
        
    Raises:
        ValueError: 如果提供者不支持或缺少api_key
    """
    # 检查提供者是否支持
    if provider not in ("openai", "linkai"):
        raise ValueError(f"Unsupported embedding provider: {provider}. Use 'openai' or 'linkai'.")

    # 使用默认模型
    model = model or "text-embedding-3-small"
    
    # 返回OpenAI兼容的提供者
    return OpenAIEmbeddingProvider(model=model, api_key=api_key, api_base=api_base)
