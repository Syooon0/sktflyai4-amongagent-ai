"""Random unique player nicknames for a single game."""

import random

MODIFIERS: tuple[str, ...] = (
    "수상한",
    "어색한",
    "이상한",
    "괴상한",
    "요상한",
    "희한한",
    "기묘한",
    "엉뚱한",
    "허술한",
    "억울한",
    "불안한",
    "심각한",
    "무심한",
    "황당한",
    "민망한",
    "애매한",
    "난감한",
    "비범한",
    "평범한",
    "소심한",
    "단호한",
    "냉정한",
    "조용한",
    "은밀한",
    "답답한",
    "당당한",
    "처량한",
    "무료한",
)

ANIMALS: tuple[str, ...] = (
    "스컹크",
    "수달",
    "토끼",
    "여우",
    "비버",
    "판다",
    "펭귄",
    "라쿤",
    "고양이",
    "부엉이",
    "햄스터",
    "미어캣",
    "쿼카",
    "알파카",
    "두더지",
    "고슴도치",
    "다람쥐",
    "카피바라",
    "나무늘보",
    "사막여우",
)


def generate_unique_nicknames(count: int = 4) -> list[str]:
    combinations = [
        f"{modifier} {animal}" for modifier in MODIFIERS for animal in ANIMALS
    ]

    if count > len(combinations):
        raise ValueError("생성 가능한 닉네임 수를 초과했습니다.")

    return random.sample(combinations, k=count)
