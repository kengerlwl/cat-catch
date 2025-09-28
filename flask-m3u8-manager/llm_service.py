#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大模型访问服务
提供与大模型API交互的核心功能
"""

import json
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime

from models import db, Prompts, Config, LLMConfig

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMService:
    """大模型服务类"""

    def __init__(self, api_url: str, api_key: str, default_model: str = "gpt-4.1",
                 default_max_tokens: int = 4096, timeout: int = 30):
        """
        初始化LLM服务

        Args:
            api_url: API接口地址
            api_key: API密钥
            default_model: 默认模型名称
            default_max_tokens: 默认最大token数
            timeout: 请求超时时间（秒）
        """
        self.api_url = api_url
        self.api_key = api_key
        self.default_model = default_model
        self.default_max_tokens = default_max_tokens
        self.timeout = timeout

        # 设置请求头
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

    def build_request(self, messages: List[Dict[str, str]], model: Optional[str] = None,
                     max_tokens: Optional[int] = None, temperature: float = 0.7,
                     stream: bool = False, **kwargs) -> Dict[str, Any]:
        """
        构建请求数据

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "问题"}]
            model: 模型名称，默认使用初始化时的模型
            max_tokens: 最大token数，默认使用初始化时的值
            temperature: 温度参数，控制回答的随机性
            stream: 是否使用流式输出
            **kwargs: 其他参数

        Returns:
            构建好的请求数据字典
        """
        request_data = {
            "model": model or self.default_model,
            "messages": messages,
            "max_tokens": max_tokens or self.default_max_tokens,
            "temperature": temperature,
            "stream": stream
        }

        # 添加其他参数
        for key, value in kwargs.items():
            if key not in request_data:
                request_data[key] = value

        logger.info(f"构建请求数据: model={request_data['model']}, "
                   f"messages_count={len(messages)}, max_tokens={request_data['max_tokens']}")

        return request_data

    def request_llm(self, messages: List[Dict[str, str]], model: Optional[str] = None,
                   max_tokens: Optional[int] = None, temperature: float = 0.7,
                   stream: bool = False, **kwargs) -> Dict[str, Any]:
        """
        请求大模型API

        Args:
            messages: 消息列表
            model: 模型名称
            max_tokens: 最大token数
            temperature: 温度参数
            stream: 是否使用流式输出
            **kwargs: 其他参数

        Returns:
            API响应结果
        """
        try:
            # 构建请求数据
            request_data = self.build_request(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=stream,
                **kwargs
            )

            logger.info(f"发送请求到: {self.api_url}")

            # 发送请求
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=request_data,
                timeout=self.timeout
            )

            # 检查响应状态
            response.raise_for_status()

            # 解析响应
            result = response.json()

            logger.info(f"请求成功，响应状态: {response.status_code}")

            return {
                "success": True,
                "data": result,
                "status_code": response.status_code,
                "timestamp": datetime.now().isoformat()
            }

        except requests.exceptions.Timeout:
            error_msg = f"请求超时 (>{self.timeout}秒)"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "timeout",
                "timestamp": datetime.now().isoformat()
            }

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP错误: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "http_error",
                "status_code": e.response.status_code,
                "timestamp": datetime.now().isoformat()
            }

        except requests.exceptions.RequestException as e:
            error_msg = f"请求异常: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "request_error",
                "timestamp": datetime.now().isoformat()
            }

        except json.JSONDecodeError as e:
            error_msg = f"JSON解析错误: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "json_error",
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            error_msg = f"未知错误: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "unknown_error",
                "timestamp": datetime.now().isoformat()
            }

    def chat_with_prompt(self, user_message: str, prompt_key: str,
                        model: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        使用数据库中的prompt与大模型对话

        Args:
            user_message: 用户消息
            prompt_key: prompt的key
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            对话结果
        """
        try:
            # 从数据库获取prompt
            system_prompt = Prompts.get_prompt(prompt_key)
            if not system_prompt:
                return {
                    "success": False,
                    "error": f"未找到prompt: {prompt_key}",
                    "error_type": "prompt_not_found",
                    "timestamp": datetime.now().isoformat()
                }

            # 构建消息列表
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]

            # 调用大模型
            return self.request_llm(messages=messages, model=model, **kwargs)

        except Exception as e:
            error_msg = f"对话处理错误: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "chat_error",
                "timestamp": datetime.now().isoformat()
            }

    def extract_content(self, response: Dict[str, Any]) -> Optional[str]:
        """
        从API响应中提取内容

        Args:
            response: API响应结果

        Returns:
            提取的内容文本，如果失败返回None
        """
        try:
            if not response.get("success"):
                return None

            data = response.get("data", {})
            choices = data.get("choices", [])

            if not choices:
                return None

            message = choices[0].get("message", {})
            content = message.get("content", "")

            return content.strip()

        except Exception as e:
            logger.error(f"内容提取错误: {str(e)}")
            return None


# 全局LLM服务实例
llm_service = None


def init_llm_service(api_url: str = None, api_key: str = None, default_model: str = None,
                    default_max_tokens: int = None, timeout: int = None):
    """
    初始化全局LLM服务实例

    Args:
        api_url: API接口地址（可选，如果不提供则从数据库读取）
        api_key: API密钥（可选，如果不提供则从数据库读取）
        default_model: 默认模型名称（可选，如果不提供则从数据库读取）
        default_max_tokens: 默认最大token数（可选，如果不提供则从数据库读取）
        timeout: 请求超时时间（秒）（可选，如果不提供则从数据库读取）
    """
    global llm_service

    # 如果没有提供参数，从数据库读取配置
    if any(param is None for param in [api_url, api_key, default_model, default_max_tokens, timeout]):
        try:
            db_config = LLMConfig.get_llm_config()
            api_url = api_url or db_config['api_url']
            api_key = api_key or db_config['api_key']
            default_model = default_model or db_config['default_model']
            default_max_tokens = default_max_tokens or db_config['default_max_tokens']
            timeout = timeout or db_config['timeout']
            logger.info("从数据库加载LLM配置")
        except Exception as e:
            logger.error(f"从数据库读取LLM配置失败: {str(e)}")
            # 使用默认值
            api_url = api_url or "https://globalai.vip/v1/chat/completions"
            api_key = api_key or ""
            default_model = default_model or "gpt-4.1"
            default_max_tokens = default_max_tokens or 4096
            timeout = timeout or 30
            logger.warning("使用默认LLM配置")

    llm_service = LLMService(
        api_url=api_url,
        api_key=api_key,
        default_model=default_model,
        default_max_tokens=default_max_tokens,
        timeout=timeout
    )
    logger.info(f"LLM服务初始化完成 - API: {api_url}, Model: {default_model}")


def init_llm_service_from_db():
    """
    从数据库配置初始化LLM服务
    """
    try:
        config = LLMConfig.get_llm_config()

        if not config['api_key']:
            logger.warning("数据库中未找到API密钥，LLM服务可能无法正常工作")

        init_llm_service(
            api_url=config['api_url'],
            api_key=config['api_key'],
            default_model=config['default_model'],
            default_max_tokens=config['default_max_tokens'],
            timeout=config['timeout']
        )

        logger.info("从数据库成功初始化LLM服务")
        return True

    except Exception as e:
        logger.error(f"从数据库初始化LLM服务失败: {str(e)}")
        return False


def reload_llm_service():
    """
    重新加载LLM服务配置（从数据库）
    """
    return init_llm_service_from_db()


def get_llm_service() -> Optional[LLMService]:
    """获取全局LLM服务实例"""
    return llm_service


# 便捷函数
def build_request(messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
    """
    构建请求数据的便捷函数

    Args:
        messages: 消息列表
        **kwargs: 其他参数

    Returns:
        构建好的请求数据
    """
    if not llm_service:
        raise RuntimeError("LLM服务未初始化，请先调用 init_llm_service()")

    return llm_service.build_request(messages, **kwargs)


def request_llm(messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
    """
    请求大模型的便捷函数

    Args:
        messages: 消息列表
        **kwargs: 其他参数

    Returns:
        API响应结果
    """
    if not llm_service:
        raise RuntimeError("LLM服务未初始化，请先调用 init_llm_service()")

    return llm_service.request_llm(messages, **kwargs)
