"""Deliberately slow demo script for CinderLens.

Showcases the classic Python performance traps so the sample report has
something interesting to chew on:

* ``fib``            - naive exponential recursion
* ``concat_loop``    - quadratic string concatenation in a loop
* ``busy_sort``      - repeated full-list sorts
* ``json_churn``     - serialize/deserialize round-trips in a loop

Run it through the profiler itself::

    python -m cinderlens profile examples/demo_slow.py \\
        --out docs/sample-report.html --json /tmp/demo_run.json --text
"""

import json
import random


def fib(n):
    """Naive recursive Fibonacci - exponential call count."""
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


def concat_loop(n):
    """Quadratic string building: ``"%s%s" % (s, i)`` always allocates a
    brand-new string, copying everything built so far, every iteration."""
    s = ""
    for i in range(n):
        s = "%s%s" % (s, i)
    return len(s)


def busy_sort(n, rounds=10):
    """Sort the same list over and over."""
    data = [random.random() for _ in range(n)]
    for _ in range(rounds):
        data = sorted(data, reverse=True)
    return data[0]


def json_churn(n, rounds=25):
    """Dump and re-parse the same payload in a loop."""
    payload = {
        "items": [
            {"id": i, "name": f"item-{i}", "tags": ["a", "b", "c"]}
            for i in range(n)
        ]
    }
    blob = json.dumps(payload)
    for _ in range(rounds):
        payload = json.loads(blob)
        blob = json.dumps(payload)
    return len(blob)


def main():
    print("fib(28)          =", fib(28))
    print("concat_loop      =", concat_loop(25000))
    print("busy_sort        =", busy_sort(150000, rounds=12))
    print("json_churn bytes =", json_churn(3000, rounds=40))


if __name__ == "__main__":
    main()
