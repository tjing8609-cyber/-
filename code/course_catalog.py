#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Course catalog text classification helpers."""

import re
from dataclasses import dataclass


DOCUMENT_RE = re.compile(r"\.(pptx?|pdf)\b", re.IGNORECASE)
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
LESSON_NUMBER_RE = re.compile(r"^\s*\d+\.\d+(?:\.\d+)?(?:\s|\n|$)")
CHAPTER_RE = re.compile(r"第[一二三四五六七八九十百千万0-9]+章[:：]?")
PROGRESS_RE = re.compile(r"(?<!\d)\d{1,3}%")

NON_VIDEO_KEYWORDS = ["见面课", "课程问答", "课程表", "成绩分析", "课程资料", "平时测试"]
ASSIGNMENT_KEYWORDS = ["作业"]


@dataclass
class CatalogClassification:
    kind: str
    reason: str = ""
    title: str = ""

    @property
    def is_video(self):
        return self.kind == "video"


def normalize_catalog_text(text):
    return "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())


def extract_catalog_title(text, max_length=80):
    text = normalize_catalog_text(text)
    text = PROGRESS_RE.sub("", text)
    text = TIME_RE.sub("", text)
    text = " ".join(text.split())
    return text[:max_length].strip()


def looks_like_chapter_header(text):
    normalized = normalize_catalog_text(text)
    if not normalized:
        return False
    if not CHAPTER_RE.search(normalized):
        return False
    if LESSON_NUMBER_RE.search(normalized):
        return False
    return len(normalized) <= 120 and len(normalized.splitlines()) <= 4


def classify_catalog_text(text):
    normalized = normalize_catalog_text(text)
    if len(normalized) < 3:
        return CatalogClassification("empty", "empty text")

    lowered = normalized.lower()
    if DOCUMENT_RE.search(lowered):
        return CatalogClassification("document", "document file", extract_catalog_title(normalized))

    if any(keyword in normalized for keyword in ASSIGNMENT_KEYWORDS):
        return CatalogClassification("assignment", "assignment item", extract_catalog_title(normalized))

    if any(keyword in normalized for keyword in NON_VIDEO_KEYWORDS):
        return CatalogClassification("navigation", "non-video navigation item", extract_catalog_title(normalized))

    if looks_like_chapter_header(normalized):
        return CatalogClassification("chapter", "chapter header", extract_catalog_title(normalized))

    if TIME_RE.search(normalized):
        return CatalogClassification("video", "has duration", extract_catalog_title(normalized))

    if LESSON_NUMBER_RE.search(normalized):
        return CatalogClassification("video", "has lesson number", extract_catalog_title(normalized))

    if "视频" in normalized or "播放" in normalized:
        return CatalogClassification("video", "has video keyword", extract_catalog_title(normalized))

    return CatalogClassification("unknown", "unknown catalog item", extract_catalog_title(normalized))
