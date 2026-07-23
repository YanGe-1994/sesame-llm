#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/8/30 15:25
@Author  : thezehui@gmail.com
@File    : jieba_service.py
"""
from dataclasses import dataclass

from injector import inject
from jieba.analyse import TFIDF

from internal.entity.jieba_entity import STOPWORD_SET


@inject
@dataclass
class JiebaService:
    """结巴分词服务"""

    # 全局 TF-IDF 实例
    _tfidf = TFIDF()

    def __post_init__(self):
        """
        初始化停用词
        """
        self._tfidf.stop_words = STOPWORD_SET

    @classmethod
    def extract_keywords(
        cls,
        text: str,
        max_keyword_pre_chunk: int = 10,
    ) -> list[str]:
        """
        根据输入文本提取关键词
        """
        return cls._tfidf.extract_tags(
            sentence=text,
            topK=max_keyword_pre_chunk,
        )