"""Small-sample statistics used by the claim guardrail. Exact where n is small; no external dependencies.

- Mann-Kendall trend test with an EXACT permutation p-value for n <= 9 (n! <= 362,880 orderings);
  normal approximation with continuity correction above that.
- Theil-Sen slope (median of pairwise slopes).
- Spearman rank correlation with an exact permutation p-value for n <= 9.
"""

from __future__ import annotations

import itertools
import math
from statistics import median


def mk_s(values: list[float]) -> int:
    s = 0
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            d = values[j] - values[i]
            s += (d > 0) - (d < 0)
    return s


def mann_kendall(values: list[float]) -> dict[str, float | int | str]:
    """One-sided test of H1: increasing trend. Values must be ordered in time."""
    n = len(values)
    s = mk_s(values)
    if n <= 9:
        # Exact null distribution of S over all orderings of the observed values (handles ties exactly).
        count_ge = total = 0
        for perm in itertools.permutations(values):
            total += 1
            if mk_s(list(perm)) >= s:
                count_ge += 1
        p = count_ge / total
        method = "exact permutation"
    else:
        var = n * (n - 1) * (2 * n + 5) / 18
        z = (s - 1) / math.sqrt(var) if s > 0 else (s + 1) / math.sqrt(var) if s < 0 else 0.0
        p = 0.5 * math.erfc(z / math.sqrt(2))
        method = "normal approximation"
    return {"n": n, "S": s, "p_one_sided": round(p, 6), "method": method}


def theil_sen(xs: list[float], ys: list[float]) -> float | None:
    slopes = [(ys[j] - ys[i]) / (xs[j] - xs[i]) for i in range(len(xs)) for j in range(i + 1, len(xs)) if xs[j] != xs[i]]
    return median(slopes) if slopes else None


def _ranks(v: list[float]) -> list[float]:
    order = sorted(range(len(v)), key=lambda i: v[i])
    ranks = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> dict[str, float | int | str | None]:
    n = len(xs)
    if n < 3:
        return {"n": n, "rho": None, "p_two_sided": None, "method": "insufficient n"}
    rx, ry = _ranks(xs), _ranks(ys)

    def rho_of(a: list[float], b: list[float]) -> float:
        ma, mb = sum(a) / n, sum(b) / n
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
        den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
        return num / den if den else 0.0

    rho = rho_of(rx, ry)
    if n <= 9:
        hits = total = 0
        for perm in itertools.permutations(ry):
            total += 1
            if abs(rho_of(rx, list(perm))) >= abs(rho) - 1e-12:
                hits += 1
        return {"n": n, "rho": round(rho, 4), "p_two_sided": round(hits / total, 6), "method": "exact permutation"}
    t = rho * math.sqrt((n - 2) / max(1e-12, 1 - rho * rho))
    p = math.erfc(abs(t) / math.sqrt(2))
    return {"n": n, "rho": round(rho, 4), "p_two_sided": round(p, 6), "method": "normal approximation"}
