from __future__ import annotations
from typing import Any, Callable, List, Optional, Literal

ReductionStrategy = Literal["normal", "applicative"]


class Redex:
    """
    A reducible expression (redex) containing an expression and its reduction function.

    Attributes:
        expr (Any): The expression to be reduced.
        reduce_fn (Callable[[Any], Any]): The function that performs the reduction.
    """

    def __init__(self, expr: Any, reduce_fn: Callable[[Any], Any]):
        self.expr = expr
        self.reduce_fn = reduce_fn

    def reduce(self) -> Any:
        return self.reduce_fn(self.expr)


class RedexHandler:
    """
    A manager for handling and reducing sequences of expressions based on
    computational reduction strategies.

    This handler supports both 'normal' (leftmost-outermost) and 'applicative'
    (leftmost-innermost) reduction orders. It allows for step-by-step reduction
    or recursive batch reduction of all registered redexes.

    Attributes:
        _redexes (List[Redex]): The internal queue of reducible expressions.

    Args:
        strategy (ReductionStrategy): The reduction rule to follow. 'normal'
            prioritizes the first items added, while 'applicative' prioritizes
            the most recent.
    """

    def __init__(self):
        self._redexes: List[Redex] = []

    def add(self, expr: Any, reduce_fn: Callable[[Any], Any]):
        self._redexes.append(Redex(expr, reduce_fn))

    def reduce_one(self, strategy: ReductionStrategy = "normal") -> Optional[Any]:
        if not self._redexes:
            return None

        index = 0 if strategy == "normal" else -1
        redex = self._redexes.pop(index)

        result = redex.reduce()

        if isinstance(result, Redex):
            self._redexes.append(result)

        return result

    def reduce_all(
        self, strategy: ReductionStrategy = "normal", max_steps: Optional[int] = None
    ) -> List[Any]:
        results: List[Any] = []
        steps = 0

        while self._redexes:
            if max_steps is not None and steps >= max_steps:
                break

            results.append(self.reduce_one(strategy))
            steps += 1

        return results

    def has_redexes(self) -> bool:
        return bool(self._redexes)

    def clear(self):
        self._redexes.clear()
