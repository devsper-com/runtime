"""Tests for map-reduce swarm runtime."""

from devsper.swarm.map_reduce import map_reduce
from devsper.swarm.swarm import Swarm


def test_map_reduce_basic():
    result = map_reduce([1, 2, 3, 4, 5], lambda x: x * 2, sum, worker_count=2)
    assert result == 30


def test_map_reduce_single_item():
    result = map_reduce([10], lambda x: x + 1, lambda xs: xs[0], worker_count=1)
    assert result == 11


def test_swarm_map_reduce():
    swarm = Swarm(worker_count=2)
    result = swarm.map_reduce([1, 2, 3], lambda x: x + 1, sum)
    assert result == 9
