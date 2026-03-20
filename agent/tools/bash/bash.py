# -*- coding: utf-8 -*-
"""
Bash命令执行工具

在工作目录中执行bash命令，返回stdout和stderr。
输出会被截断到最后N行或NK字节。
大输出会保存到临时文件。

环境变量自动从 ~/.cow/.env 注入。
"""

# 导入操作系统模块
import os

# 导入正则表达式模块
import re

# 导入系统模块
import sys

# 导入子进程模块
import subprocess

# 导入临时文件模块
import tempfile

# 导入类型提示
from typing import Dict, Any

# 导入工具基类和结果类
from agent.tools.base_tool import BaseTool, ToolResult

# 导入截断工具
from agent.tools.utils.truncate import truncate_tail, format_size, DEFAULT_MAX_LINES, DEFAULT_MAX_BYTES

# 导入日志模块
from common.log import logger

# 导入路径扩展工具
from common.utils import expand_path


class Bash(BaseTool):
    """
    Bash命令执行工具类
    
    功能：
    - 执行bash命令
    - 自动注入环境变量
    - 截断大输出
    - 安全检查
    
    安全规则：
    - 允许在工作区内自由创建/修改/删除文件
    - 破坏性和工作区外的命令需要确认
    """

    # 工具名称
    name: str = "bash"
    
    # 工具描述
    description: str = f"""Execute a bash command in the current working directory. Returns stdout and stderr. Output is truncated to last {DEFAULT_MAX_LINES} lines or {DEFAULT_MAX_BYTES // 1024}KB (whichever is hit first). If truncated, full output is saved to a temp file.

ENVIRONMENT: All API keys from env_config are auto-injected. Use $VAR_NAME directly.

SAFETY:
- Freely create/modify/delete files within the workspace
- For destructive and out-of-workspace commands, explain and confirm first"""

    # 参数JSON Schema
    params: dict = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Bash command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (optional, default: 30)"
            }
        },
        "required": ["command"]
    }

    def __init__(self, config: dict = None):
        """
        初始化Bash工具
        
        Args:
            config: 配置字典，可包含：
                - cwd: 工作目录
                - timeout: 默认超时时间
                - safety_mode: 安全模式开关
        """
        # 存储配置
        self.config = config or {}
        # 获取工作目录
        self.cwd = self.config.get("cwd", os.getcwd())
        # 确保工作目录存在
        if not os.path.exists(self.cwd):
            os.makedirs(self.cwd, exist_ok=True)
        # 获取默认超时时间
        self.default_timeout = self.config.get("timeout", 30)
        # 启用安全模式（默认启用，可在配置中禁用）
        self.safety_mode = self.config.get("safety_mode", True)

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """
        执行bash命令
        
        Args:
            args: 包含命令和可选超时时间
                - command: 要执行的命令
                - timeout: 超时时间（秒）
            
        Returns:
            ToolResult: 命令输出或错误
        """
        # 获取参数
        command = args.get("command", "").strip()        # 命令
        timeout = args.get("timeout", self.default_timeout)  # 超时时间

        # 检查命令参数
        if not command:
            return ToolResult.fail("Error: command parameter is required")

        # 安全检查：防止访问敏感配置文件
        if "~/.cow/.env" in command or "~/.cow" in command:
            return ToolResult.fail(
                "Error: Access denied. API keys and credentials must be accessed through the env_config tool only."
            )

        # 可选安全检查 - 只对极其危险的命令发出警告
        if self.safety_mode:
            warning = self._get_safety_warning(command)
            if warning:
                return ToolResult.fail(
                    f"Safety Warning: {warning}\n\nIf you believe this command is safe and necessary, please ask the user for confirmation first, explaining what the command does and why it's needed.")

        try:
            # 准备环境变量（复制当前环境）
            env = os.environ.copy()
            
            # 从 ~/.cow/.env 加载环境变量
            env_file = expand_path("~/.cow/.env")
            dotenv_vars = {}
            if os.path.exists(env_file):
                try:
                    from dotenv import dotenv_values
                    # 读取.env文件中的变量
                    dotenv_vars = dotenv_values(env_file)
                    # 更新环境变量
                    env.update(dotenv_vars)
                    logger.debug(f"[Bash] Loaded {len(dotenv_vars)} variables from {env_file}")
                except ImportError:
                    # python-dotenv未安装
                    logger.debug("[Bash] python-dotenv not installed, skipping .env loading")
                except Exception as e:
                    # 其他错误
                    logger.debug(f"[Bash] Failed to load .env: {e}")

            # 记录进程信息
            # getuid() 只在类Unix系统上存在
            if hasattr(os, 'getuid'):
                logger.debug(f"[Bash] Process UID: {os.getuid()}")
            else:
                logger.debug(f"[Bash] Process User: {os.environ.get('USERNAME', os.environ.get('USER', 'unknown'))}")
            
            # Windows平台特殊处理
            if sys.platform == "win32":
                # 设置Python编码
                env["PYTHONIOENCODING"] = "utf-8"
                # 转换环境变量引用为Windows格式
                command = self._convert_env_vars_for_windows(command, dotenv_vars)
                # 添加代码页设置
                if command and not command.strip().lower().startswith("chcp"):
                    command = f"chcp 65001 >nul 2>&1 && {command}"

            # 执行命令（继承环境变量）
            result = subprocess.run(
                command,                        # 命令字符串
                shell=True,                     # 使用shell执行
                cwd=self.cwd,                   # 工作目录
                stdout=subprocess.PIPE,         # 捕获stdout
                stderr=subprocess.PIPE,         # 捕获stderr
                text=True,                      # 文本模式
                encoding="utf-8",               # 编码
                errors="replace",               # 错误处理
                timeout=timeout,                # 超时时间
                env=env                         # 环境变量
            )
            
            # 记录执行结果
            logger.debug(f"[Bash] Exit code: {result.returncode}")
            logger.debug(f"[Bash] Stdout length: {len(result.stdout)}")
            logger.debug(f"[Bash] Stderr length: {len(result.stderr)}")
            
            # 处理退出码126且无输出的情况
            if result.returncode == 126 and not result.stdout and not result.stderr:
                logger.warning(f"[Bash] Exit 126 with no output - trying alternative execution method")
                # 尝试使用参数列表而非shell=True
                import shlex
                try:
                    parts = shlex.split(command)
                    if len(parts) > 0:
                        logger.info(f"[Bash] Retrying with argument list: {parts[:3]}...")
                        retry_result = subprocess.run(
                            parts,                      # 参数列表
                            cwd=self.cwd,               # 工作目录
                            stdout=subprocess.PIPE,     # 捕获stdout
                            stderr=subprocess.PIPE,     # 捕获stderr
                            text=True,                  # 文本模式
                            encoding="utf-8",           # 编码
                            errors="replace",           # 错误处理
                            timeout=timeout,            # 超时时间
                            env=env                     # 环境变量
                        )
                        logger.debug(f"[Bash] Retry exit code: {retry_result.returncode}, stdout: {len(retry_result.stdout)}, stderr: {len(retry_result.stderr)}")
                        
                        # 如果重试成功，使用重试结果
                        if retry_result.returncode == 0 or retry_result.stdout or retry_result.stderr:
                            result = retry_result
                        else:
                            # 两次尝试都失败 - 检查是否是vision技能
                            if 'openai-image-vision' in command or 'vision.sh' in command:
                                # 创建模拟结果，提供友好错误消息
                                from types import SimpleNamespace
                                result = SimpleNamespace(
                                    returncode=1,
                                    stdout='{"error": "图片无法解析", "reason": "该图片格式可能不受支持，或图片文件存在问题", "suggestion": "请尝试其他图片"}',
                                    stderr=''
                                )
                                logger.info(f"[Bash] Converted exit 126 to user-friendly image error message for vision skill")
                except Exception as retry_err:
                    logger.warning(f"[Bash] Retry failed: {retry_err}")

            # 合并stdout和stderr
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            # 检查是否需要保存完整输出到临时文件
            temp_file_path = None
            total_bytes = len(output.encode('utf-8'))

            if total_bytes > DEFAULT_MAX_BYTES:
                # 保存完整输出到临时文件
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log', prefix='bash-') as f:
                    f.write(output)
                    temp_file_path = f.name

            # 应用尾部截断
            truncation = truncate_tail(output)
            output_text = truncation.content or "(no output)"

            # 构建结果详情
            details = {}

            if truncation.truncated:
                details["truncation"] = truncation.to_dict()
                if temp_file_path:
                    details["full_output_path"] = temp_file_path

                # 构建提示信息
                start_line = truncation.total_lines - truncation.output_lines + 1
                end_line = truncation.total_lines

                if truncation.last_line_partial:
                    # 边界情况：最后一行单独超过30KB
                    last_line = output.split('\n')[-1] if output else ""
                    last_line_size = format_size(len(last_line.encode('utf-8')))
                    output_text += f"\n\n[Showing last {format_size(truncation.output_bytes)} of line {end_line} (line is {last_line_size}). Full output: {temp_file_path}]"
                elif truncation.truncated_by == "lines":
                    output_text += f"\n\n[Showing lines {start_line}-{end_line} of {truncation.total_lines}. Full output: {temp_file_path}]"
                else:
                    output_text += f"\n\n[Showing lines {start_line}-{end_line} of {truncation.total_lines} ({format_size(DEFAULT_MAX_BYTES)} limit). Full output: {temp_file_path}]"

            # 检查退出码
            if result.returncode != 0:
                output_text += f"\n\nCommand exited with code {result.returncode}"
                return ToolResult.fail({
                    "output": output_text,                # 输出内容
                    "exit_code": result.returncode,       # 退出码
                    "details": details if details else None  # 详情
                })

            return ToolResult.success({
                "output": output_text,                    # 输出内容
                "exit_code": result.returncode,           # 退出码
                "details": details if details else None   # 详情
            })

        except subprocess.TimeoutExpired:
            # 超时错误
            return ToolResult.fail(f"Error: Command timed out after {timeout} seconds")
        except Exception as e:
            # 其他错误
            return ToolResult.fail(f"Error executing command: {str(e)}")

    def _get_safety_warning(self, command: str) -> str:
        """
        获取潜在危险命令的安全警告
        
        只对极其危险的系统级操作发出警告
        
        Args:
            command: 要检查的命令
            
        Returns:
            str: 如果危险返回警告消息，安全返回空字符串
        """
        # 转换为小写并去除首尾空白
        cmd_lower = command.lower().strip()

        # 只阻止极其危险的系统操作
        dangerous_patterns = [
            # 系统关机/重启
            ("shutdown", "This command will shut down the system"),
            ("reboot", "This command will reboot the system"),
            ("halt", "This command will halt the system"),
            ("poweroff", "This command will power off the system"),

            # 关键系统修改
            ("rm -rf /", "This command will delete the entire filesystem"),
            ("rm -rf /*", "This command will delete the entire filesystem"),
            ("dd if=/dev/zero", "This command can destroy disk data"),
            ("mkfs", "This command will format a filesystem, destroying all data"),
            ("fdisk", "This command modifies disk partitions"),

            # 用户/系统管理（仅当目标是系统用户时）
            ("userdel root", "This command will delete the root user"),
            ("passwd root", "This command will change the root password"),
        ]

        # 检查危险模式
        for pattern, warning in dangerous_patterns:
            if pattern in cmd_lower:
                return warning

        # 检查工作区外的递归删除
        if "rm" in cmd_lower and "-rf" in cmd_lower:
            # 允许在当前工作区内删除
            if not any(path in cmd_lower for path in ["./", self.cwd.lower()]):
                # 检查是否针对系统目录
                system_dirs = ["/bin", "/usr", "/etc", "/var", "/home", "/root", "/sys", "/proc"]
                if any(sysdir in cmd_lower for sysdir in system_dirs):
                    return "This command will recursively delete system directories"

        return ""  # 无需警告

    @staticmethod
    def _convert_env_vars_for_windows(command: str, dotenv_vars: dict) -> str:
        """
        将bash风格的 $VAR / ${VAR} 引用转换为cmd.exe的 %VAR% 语法
        
        只转换从.env加载的变量（用户配置的API密钥等），
        避免破坏 $PATH、jq表达式、正则表达式等。
        
        Args:
            command: 原始命令
            dotenv_vars: .env中加载的变量字典
            
        Returns:
            str: 转换后的命令
        """
        # 如果没有变量需要转换，直接返回
        if not dotenv_vars:
            return command

        def replace_match(m):
            """替换匹配的环境变量引用"""
            # 获取变量名（从group(1)或group(2)）
            var_name = m.group(1) or m.group(2)
            # 只转换.env中存在的变量
            if var_name in dotenv_vars:
                return f"%{var_name}%"
            # 其他变量保持原样
            return m.group(0)

        # 替换 ${VAR} 或 $VAR 格式的引用
        return re.sub(r'\$\{(\w+)\}|\$(\w+)', replace_match, command)
