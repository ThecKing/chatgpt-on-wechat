# -*- coding: utf-8 -*-
"""
有序字典模块

实现了一个基于堆（Heap）的有序字典（SortedDict）类。
继承自Python内置的dict，额外提供以下特性：
1. 字典中的键值对按键的排序顺序存储
2. 支持自定义排序函数（sort_func）
3. 支持升序或降序排列
4. 高效的插入、删除、查找操作（基于堆结构）

应用场景：
- 插件系统：按优先级管理插件
- 任务队列：按优先级管理任务
- 配置管理：按优先级处理配置项

核心原理：
使用Python的heapq模块（最小堆）来维护有序性。
堆中存储(优先级, 键)的元组，通过sort_func计算每个键的优先级。
"""

# 导入heapq模块，提供高效的堆操作功能
# 堆是一种特殊的完全二叉树，适合实现优先队列
import heapq


class SortedDict(dict):
    """
    有序字典类
    
    继承自dict，额外维护一个堆结构来保持键的有序排列。
    
    与普通字典的区别：
    - 迭代时按键的排序顺序返回
    - 支持自定义排序函数
    - 支持升序/降序排列
    
    属性说明：
    - sort_func: 排序函数，接收(key, value)，返回用于排序的值
    - sorted_keys: 缓存的排序后的键列表
    - reverse: 是否降序排列
    - heap: 堆结构，存储(优先级, 键)的元组
    
    示例：
        # 按优先级降序排列插件
        sd = SortedDict(lambda k, v: v.priority, reverse=True)
        sd['plugin1'] = Plugin(priority=10)
        sd['plugin2'] = Plugin(priority=5)
        # 迭代顺序：plugin1, plugin2（优先级10 > 5）
    """
    
    def __init__(self, sort_func=lambda k, v: k, init_dict=None, reverse=False):
        """
        初始化有序字典
        
        Args:
            sort_func: 排序函数，接收(key, value)参数，返回用于排序的值
                      默认使用键本身进行排序
            init_dict: 初始字典或键值对列表
            reverse: 是否降序排列，默认为False（升序）
        """
        # 如果init_dict为None，设为空列表
        if init_dict is None:
            init_dict = []
            
        # 如果init_dict是普通字典，转换为键值对列表
        if isinstance(init_dict, dict):
            init_dict = init_dict.items()
            
        # 保存排序函数
        self.sort_func = sort_func
        
        # 初始化缓存键为None（懒加载）
        self.sorted_keys = None
        
        # 保存降序标志
        self.reverse = reverse
        
        # 初始化堆结构（存储元组：优先级, 键）
        self.heap = []
        
        # 遍历初始数据，调用__setitem__添加到字典
        # 这里会触发排序逻辑
        for k, v in init_dict:
            self[k] = v

    def __setitem__(self, key, value):
        """
        设置字典项
        
        如果键已存在，更新值并调整堆中优先级。
        如果键不存在，插入新值并添加到堆中。
        
        Args:
            key: 键
            value: 值
        """
        # 检查键是否已存在
        if key in self:
            # 键已存在：更新值
            # 调用父类的__setitem__更新字典
            super().__setitem__(key, value)
            
            # 遍历堆找到该键的位置
            for i, (priority, k) in enumerate(self.heap):
                if k == key:
                    # 更新堆中该键的优先级
                    self.heap[i] = (self.sort_func(key, value), key)
                    # 重新堆化（保持堆性质）
                    heapq.heapify(self.heap)
                    break
            # 缓存已失效，需要重新排序
            self.sorted_keys = None
        else:
            # 键不存在：插入新值
            # 调用父类的__setitem__添加到字典
            super().__setitem__(key, value)
            
            # 将新键添加到堆中
            heapq.heappush(self.heap, (self.sort_func(key, value), key))
            # 缓存已失效
            self.sorted_keys = None

    def __delitem__(self, key):
        """
        删除字典项
        
        从字典和堆中同时移除该项。
        
        Args:
            key: 要删除的键
            
        Raises:
            KeyError: 如果键不存在
        """
        # 调用父类的__delitem__从字典中删除
        super().__delitem__(key)
        
        # 遍历堆找到该键的位置
        for i, (priority, k) in enumerate(self.heap):
            if k == key:
                # 从堆中删除该项
                del self.heap[i]
                # 重新堆化
                heapq.heapify(self.heap)
                break
        # 缓存已失效
        self.sorted_keys = None

    def keys(self):
        """
        获取排序后的键列表
        
        使用缓存机制避免频繁排序。
        只有当缓存失效（sorted_keys为None）时才重新排序。
        
        Returns:
            排序后的键列表
        """
        # 检查缓存是否有效
        if self.sorted_keys is None:
            # 缓存无效，根据reverse标志进行排序
            # sorted()返回一个列表，(_, k)表示只取键部分
            self.sorted_keys = [k for _, k in sorted(self.heap, reverse=self.reverse)]
            
        # 返回排序后的键列表
        return self.sorted_keys

    def items(self):
        """
        获取排序后的键值对列表
        
        Returns:
            排序后的键值对列表，每个元素为(key, value)元组
        """
        # 检查缓存是否有效
        if self.sorted_keys is None:
            # 缓存无效，重新排序
            self.sorted_keys = [k for _, k in sorted(self.heap, reverse=self.reverse)]
            
        # 根据排序后的键列表构建键值对列表
        sorted_items = [(k, self[k]) for k in self.sorted_keys]
        
        return sorted_items

    def _update_heap(self, key):
        """
        更新堆中指定键的优先级
        
        当键的值发生变化（但键本身不变）时调用，
        用于更新堆中的优先级信息。
        
        Args:
            key: 要更新的键
        """
        # 遍历堆找到该键
        for i, (priority, k) in enumerate(self.heap):
            if k == key:
                # 计算新的优先级
                new_priority = self.sort_func(key, self[key])
                
                # 如果优先级发生变化
                if new_priority != priority:
                    # 更新堆中的优先级
                    self.heap[i] = (new_priority, key)
                    # 重新堆化
                    heapq.heapify(self.heap)
                    # 标记缓存失效
                    self.sorted_keys = None
                break

    def __iter__(self):
        """
        迭代器支持
        
        使得可以像普通字典一样迭代：
        for key in sorted_dict:
            ...
            
        Returns:
            键的迭代器
        """
        # 调用keys()方法返回排序后的键迭代器
        return iter(self.keys())

    def __repr__(self):
        """
        返回对象的字符串表示
        
        用于调试和打印显示。
        
        Returns:
            字符串表示，格式如：SortedDict({...}, sort_func=xxx, reverse=True)
        """
        # 构建字符串表示
        # type(self).__name__ 获取类名（SortedDict）
        # dict(self) 获取字典内容
        # self.sort_func.__name__ 获取排序函数名
        return f"{type(self).__name__}({dict(self)}, sort_func={self.sort_func.__name__}, reverse={self.reverse})"
