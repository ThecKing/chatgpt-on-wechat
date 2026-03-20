# -*- coding: utf-8 -*-
"""
Agent技能模块

提供技能的加载、管理和执行框架。
技能是带有前置元数据的Markdown文件，提供特定任务的专业指导。

主要组件：
- Skill: 技能数据结构
- SkillLoader: 技能加载器
- SkillManager: 技能管理器
- SkillService: 技能服务
- format_skills_for_prompt: 格式化技能为提示词
"""

# 导入技能类型定义
from agent.skills.types import (
    Skill,                 # 技能数据类
    SkillEntry,            # 技能条目
    SkillMetadata,         # 技能元数据
    SkillInstallSpec,      # 技能安装规格
    LoadSkillsResult,      # 加载结果
)

# 导入技能加载器
from agent.skills.loader import SkillLoader

# 导入技能管理器
from agent.skills.manager import SkillManager

# 导入技能服务
from agent.skills.service import SkillService

# 导入技能格式化函数
from agent.skills.formatter import format_skills_for_prompt

# 公开导出的类和函数
__all__ = [
    "Skill",                # 技能数据类
    "SkillEntry",           # 技能条目
    "SkillMetadata",        # 技能元数据
    "SkillInstallSpec",     # 安装规格
    "LoadSkillsResult",     # 加载结果
    "SkillLoader",          # 加载器
    "SkillManager",         # 管理器
    "SkillService",         # 服务
    "format_skills_for_prompt",  # 格式化函数
]
