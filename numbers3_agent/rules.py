"""Official Numbers3 odds and grading, preserving leading zeroes."""
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from math import factorial, prod
import re

PRICE_YEN = 200
OUTCOMES = 1_000

class Play(str, Enum):
    STRAIGHT = "straight"
    BOX = "box"
    SET = "set"
    MINI = "mini"

def three_digits(number: str) -> str:
    if not isinstance(number, str) or not re.fullmatch(r"[0-9]{3}", number):
        raise ValueError("Numbers3 result must be exactly three digits, including zeroes")
    return number

def validate_play(number: str, mode: str | Play) -> tuple[str, Play]:
    try:
        selected = Play(mode)
    except (TypeError, ValueError) as exc:
        raise ValueError("mode must be straight, box, set, or mini") from exc
    if selected is Play.MINI:
        if not isinstance(number, str) or not re.fullmatch(r"[0-9]{2}", number):
            raise ValueError("mini entry must be exactly two digits")
    else:
        three_digits(number)
        if selected in (Play.BOX, Play.SET) and len(set(number)) == 1:
            raise ValueError("three matching digits cannot be used for box or set")
    return number, selected

def permutations(number: str) -> int:
    three_digits(number)
    counts = Counter(number)
    return factorial(3) // prod(factorial(v) for v in counts.values())

@dataclass(frozen=True)
class Odds:
    straight: float
    box_only: float
    any_win: float
    combinations: int

def odds(number: str, mode: str | Play) -> Odds:
    number, mode = validate_play(number, mode)
    if mode is Play.MINI:
        return Odds(0, 0, 1 / 100, 10)
    if mode is Play.STRAIGHT:
        return Odds(1 / OUTCOMES, 0, 1 / OUTCOMES, 1)
    ways = permutations(number)
    if mode is Play.BOX:
        return Odds(0, ways / OUTCOMES, ways / OUTCOMES, ways)
    return Odds(1 / OUTCOMES, (ways - 1) / OUTCOMES, ways / OUTCOMES, ways)

def grade(number: str, actual: str, mode: str | Play) -> str:
    number, mode = validate_play(number, mode)
    actual = three_digits(actual)
    if mode is Play.MINI:
        return "mini" if number == actual[-2:] else "miss"
    if number == actual:
        return {Play.STRAIGHT: "straight", Play.BOX: "box",
                Play.SET: "set_straight"}[mode]
    if mode in (Play.BOX, Play.SET) and sorted(number) == sorted(actual):
        return "box" if mode is Play.BOX else "set_box"
    return "miss"
