from __future__ import annotations

import heapq
from math import hypot
from typing import Any

from .grid import NavigationGrid

_NEIGHBORS = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))


def astar_path(grid: NavigationGrid, start: tuple[float, float], goal: tuple[float, float],
               turn_penalty: float = 0.0) -> dict[str, Any]:
    """Find a deterministic 8-connected route, optionally penalizing direction changes."""
    start_cell = grid.nearest_traversable(start)
    goal_cell = grid.nearest_traversable(goal)
    if start_cell is None or goal_cell is None:
        return {"found": False, "coordinates": [], "explored_nodes": 0}
    if start_cell == goal_cell:
        if start == goal:
            return {"found": False, "coordinates": [], "explored_nodes": 1}
        return {"found": True, "coordinates": [start, goal], "explored_nodes": 1,
                "cells": [start_cell], "turn_penalty": turn_penalty, "route_cost": hypot(goal[0] - start[0], goal[1] - start[1])}
    start_state = (start_cell, -1)
    open_set: list[tuple[float, float, int, int, int]] = []
    heuristic = hypot(start_cell[0] - goal_cell[0], start_cell[1] - goal_cell[1]) * grid.resolution
    heapq.heappush(open_set, (heuristic, 0.0, start_cell[0], start_cell[1], -1))
    came_from: dict[tuple[tuple[int, int], int], tuple[tuple[int, int], int]] = {}
    cost_so_far = {start_state: 0.0}
    explored = 0
    while open_set:
        _, current_cost, x, y, previous_direction = heapq.heappop(open_set)
        current = (x, y)
        current_state = (current, previous_direction)
        if current_cost > cost_so_far.get(current_state, float("inf")):
            continue
        explored += 1
        if current == goal_cell:
            states = [current_state]
            while states[-1] in came_from:
                states.append(came_from[states[-1]])
            states.reverse()
            cells = [state[0] for state in states]
            points = [grid.center(cell) for cell in cells]
            points[0], points[-1] = start, goal
            return {"found": True, "coordinates": points, "explored_nodes": explored, "cells": cells,
                    "turn_penalty": turn_penalty, "route_cost": current_cost}
        for direction, (dx, dy) in enumerate(_NEIGHBORS):
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor not in grid.traversable:
                continue
            if dx and dy and ((current[0] + dx, current[1]) not in grid.traversable or
                              (current[0], current[1] + dy) not in grid.traversable):
                continue
            step_cost = grid.resolution * (1.41421356237 if dx and dy else 1.0)
            if previous_direction not in {-1, direction}:
                step_cost += turn_penalty
            neighbor_state = (neighbor, direction)
            candidate = current_cost + step_cost
            if candidate >= cost_so_far.get(neighbor_state, float("inf")):
                continue
            came_from[neighbor_state] = current_state
            cost_so_far[neighbor_state] = candidate
            heuristic = hypot(neighbor[0] - goal_cell[0], neighbor[1] - goal_cell[1]) * grid.resolution
            heapq.heappush(open_set, (candidate + heuristic, candidate, neighbor[0], neighbor[1], direction))
    return {"found": False, "coordinates": [], "explored_nodes": explored}
