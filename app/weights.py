class WeightError(ValueError):
    pass


def distribute(pinned: list[int | None]) -> list[int]:
    """Веса офферов потока. На входе по элементу на оффер: закреплённый вес или None (не закреплён).

    Keitaro принимает только целые share, поэтому остаток от деления раздаём по 1 первым: 100/3 -> 34/33/33.
    """
    pinned_sum = sum(s for s in pinned if s is not None)
    free = pinned.count(None)
    if pinned_sum > 100:
        raise WeightError(f"Сумма закреплённых весов {pinned_sum}% больше 100%")
    rest = 100 - pinned_sum
    if free == 0:
        if pinned and rest != 0:
            raise WeightError(f"Все офферы закреплены, но сумма {pinned_sum}% не равна 100%")
        return list(pinned)
    if rest == 0:
        raise WeightError("Закреплённые офферы занимают 100%, незакреплённым ничего не остаётся")
    base, extra = divmod(rest, free)
    result = []
    for s in pinned:
        if s is None:
            s = base + (1 if extra > 0 else 0)
            extra -= 1
        result.append(s)
    return result
