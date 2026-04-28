#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Controlled quiz automation policy for video quiz popups."""

from dataclasses import dataclass
from typing import Iterable, List, Optional


VALID_MODES = {"manual", "assist", "semi_auto", "auto_practice"}


@dataclass
class QuizAgentDecision:
    should_select: bool
    should_close: bool
    letters: List[str]
    mode: str
    reason: str = ""


def normalize_answer_mode(mode: Optional[str], default="assist"):
    mode = (mode or default).strip().lower()
    aliases = {
        "auto": "auto_practice",
        "full_auto": "auto_practice",
        "semi": "semi_auto",
        "semi-automatic": "semi_auto",
    }
    mode = aliases.get(mode, mode)
    return mode if mode in VALID_MODES else default


def normalize_letters(letters: Optional[Iterable[str]], option_count: int) -> List[str]:
    if not letters:
        return []
    allowed = [chr(ord("A") + i) for i in range(max(0, option_count))]
    result = []
    for letter in letters:
        value = str(letter).strip().upper()
        if value in allowed and value not in result:
            result.append(value)
    return result


class QuizAutomationAgent:
    def __init__(self, mode="assist", logger=None):
        self.mode = normalize_answer_mode(mode)
        self.logger = logger

    def decide(self, letters=None, option_count=0, source="visible_answer") -> QuizAgentDecision:
        normalized = normalize_letters(letters, option_count)
        if not normalized:
            return QuizAgentDecision(
                should_select=False,
                should_close=False,
                letters=[],
                mode=self.mode,
                reason="no reliable answer letters",
            )

        if self.mode == "manual":
            return QuizAgentDecision(
                should_select=False,
                should_close=False,
                letters=normalized,
                mode=self.mode,
                reason="manual mode requires user handling",
            )

        if self.mode == "assist":
            return QuizAgentDecision(
                should_select=False,
                should_close=False,
                letters=normalized,
                mode=self.mode,
                reason="assist mode only reports suggested answer",
            )

        if self.mode == "semi_auto":
            return QuizAgentDecision(
                should_select=False,
                should_close=False,
                letters=normalized,
                mode=self.mode,
                reason="semi_auto requires explicit user confirmation before clicking",
            )

        if self.mode == "auto_practice" and source == "visible_answer":
            return QuizAgentDecision(
                should_select=True,
                should_close=True,
                letters=normalized,
                mode=self.mode,
                reason="auto_practice can select visible popup answers",
            )

        return QuizAgentDecision(
            should_select=False,
            should_close=False,
            letters=normalized,
            mode=self.mode,
            reason="mode does not allow automatic selection for this source",
        )
