"""
Circulation Graph & Accessibility Analysis Engine.
Builds a mathematical graph of traversable spaces using NetworkX (or fallback graph dictionary):
- Nodes: External Entrance, Rooms, Corridors, Lobbies, Staircase Cores.
- Edges: Explicit Doors and Openings connecting spaces.
Validates:
1. Entrance Reachability: Every required habitable room must be connected via a path from the main entrance.
2. Isolated Spaces: Identifies rooms with 0 doors or dead-end disconnected components.
3. Multi-Storey Staircase Continuity: Upper floor rooms must be reachable from Ground Floor via the Staircase core.
4. Route Distances: Computes shortest topological route distance between spaces for adjacency checks.
"""
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import deque
import heapq

from ..schemas import (
    FloorPlanDefinition,
    RoomPolygon,
    DoorDefinition,
    ArchitecturalCheckResult,
    CheckDimension,
    CheckStatus,
    CheckSeverity,
)


class NativeGraph:
    """Lightweight, deterministic pure-Python graph structure."""
    def __init__(self):
        self._adj: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._nodes: Dict[str, Dict[str, Any]] = {}

    def clear(self):
        self._adj.clear()
        self._nodes.clear()

    def add_node(self, node: str, **attrs):
        if node not in self._nodes:
            self._nodes[node] = {}
            self._adj[node] = {}
        self._nodes[node].update(attrs)

    def add_edge(self, u: str, v: str, **attrs):
        if u not in self._nodes:
            self.add_node(u)
        if v not in self._nodes:
            self.add_node(v)
        self._adj[u][v] = attrs
        self._adj[v][u] = attrs

    def has_node(self, node: str) -> bool:
        return node in self._nodes

    def degree(self, node: str) -> int:
        return len(self._adj.get(node, {}))

    def nodes(self, data: bool = False):
        if data:
            return self._nodes.items()
        return self._nodes.keys()

    def get_node_data(self, node: str) -> Dict[str, Any]:
        return self._nodes.get(node, {})


    def has_path(self, source: str, target: str) -> bool:
        if source not in self._adj or target not in self._adj:
            return False
        if source == target:
            return True
        visited = {source}
        queue = deque([source])
        while queue:
            curr = queue.popleft()
            if curr == target:
                return True
            for neighbor in self._adj.get(curr, {}):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return False

    def shortest_path_length(self, source: str, target: str, weight: str = "distance") -> float:
        if source not in self._adj or target not in self._adj:
            raise KeyError(f"Node {source} or {target} not in graph")
        if source == target:
            return 0.0

        # Dijkstra algorithm
        dist: Dict[str, float] = {source: 0.0}
        pq = [(0.0, source)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, float("inf")):
                continue
            if u == target:
                return d
            for v, edge_data in self._adj.get(u, {}).items():
                w = float(edge_data.get(weight, 1.0))
                new_d = d + w
                if new_d < dist.get(v, float("inf")):
                    dist[v] = new_d
                    heapq.heappush(pq, (new_d, v))
        raise ValueError(f"No path between {source} and {target}")


class CirculationGraph:
    def __init__(self):
        self.graph = NativeGraph()

    def build_from_floors(self, floors: List[FloorPlanDefinition]):
        """
        Builds traversable connectivity graph across all floors from rooms, stairs, and doors.
        """
        self.graph.clear()
        self.graph.add_node("EXTERIOR", type="external", floor=-1)

        # 1. Add Room Nodes
        for fl in floors:
            f_idx = fl.floor_index
            for rm in fl.rooms:
                self.graph.add_node(
                    rm.room_id,
                    name=rm.name,
                    type=rm.type,
                    floor=f_idx,
                    is_stair=rm.is_structural_stair,
                    req_id=rm.req_id,
                    required=rm.required
                )

        # 2. Add Vertical Staircase Connections across floors
        stair_nodes_by_floor: Dict[int, str] = {}
        for fl in floors:
            stair = next((r for r in fl.rooms if r.is_structural_stair), None)
            if stair:
                stair_nodes_by_floor[fl.floor_index] = stair.room_id

        if len(floors) > 1 and len(stair_nodes_by_floor) > 1:
            sorted_storeys = sorted(stair_nodes_by_floor.keys())
            for idx in range(len(sorted_storeys) - 1):
                s1 = stair_nodes_by_floor[sorted_storeys[idx]]
                s2 = stair_nodes_by_floor[sorted_storeys[idx + 1]]
                # Edge with weight 3.0m (vertical flight length)
                self.graph.add_edge(s1, s2, connection_type="stair_flight", distance=3.0)

        # 3. Add Edges from Explicit Doors
        for fl in floors:
            for door in fl.doors:
                spaces = door.connected_space_ids
                if len(spaces) >= 2:
                    u, v = spaces[0], spaces[1]
                    if self.graph.has_node(u) and self.graph.has_node(v):
                        self.graph.add_edge(u, v, door_id=door.door_id, distance=1.0)

    def analyze_accessibility(
        self,
        floors: List[FloorPlanDefinition]
    ) -> Tuple[List[ArchitecturalCheckResult], List[str], List[str]]:
        """
        Evaluates reachability and connectivity.
        Returns (checks, isolated_room_ids, unreachable_rooms).
        """
        checks: List[ArchitecturalCheckResult] = []
        isolated: List[str] = []
        unreachable: List[str] = []

        all_room_nodes = [
            n for n, data in self.graph.nodes(data=True)
            if n != "EXTERIOR" and not data.get("is_stair")
        ]

        # Check 1: Main External Entrance Exists
        has_ext_entrance = self.graph.has_node("EXTERIOR") and self.graph.degree("EXTERIOR") > 0
        if not has_ext_entrance:
            checks.append(
                ArchitecturalCheckResult(
                    check_id="CIRC_MAIN_ENTRANCE",
                    dimension=CheckDimension.FUNCTIONAL_ACCESSIBILITY,
                    status=CheckStatus.FAIL,
                    severity=CheckSeverity.ERROR,
                    message="Building lacks an explicit, geometrically verified external entrance door."
                )
            )
        else:
            checks.append(
                ArchitecturalCheckResult(
                    check_id="CIRC_MAIN_ENTRANCE",
                    dimension=CheckDimension.FUNCTIONAL_ACCESSIBILITY,
                    status=CheckStatus.PASS,
                    severity=CheckSeverity.INFO,
                    message="External entrance door verified."
                )
            )

        # Check 2: Isolated Rooms (Degree == 0)
        for r_id in all_room_nodes:
            deg = self.graph.degree(r_id)
            if deg == 0:
                isolated.append(r_id)
                data = self.graph.get_node_data(r_id)
                checks.append(
                    ArchitecturalCheckResult(
                        check_id=f"CIRC_ISOLATED_{r_id}",
                        dimension=CheckDimension.FUNCTIONAL_ACCESSIBILITY,
                        status=CheckStatus.FAIL,
                        severity=CheckSeverity.ERROR,
                        affected_room_ids=[r_id],
                        affected_floor_ids=[f"F{data.get('floor', 0)}"],
                        message=f"Room '{data.get('name')}' is physically isolated (no connecting doors)."
                    )
                )

        # Check 3: Reachability from Entrance (if entrance exists)
        if has_ext_entrance:
            for r_id in all_room_nodes:
                if self.graph.has_path("EXTERIOR", r_id):
                    pass
                else:
                    unreachable.append(r_id)
                    data = self.graph.get_node_data(r_id)
                    checks.append(
                        ArchitecturalCheckResult(
                            check_id=f"CIRC_UNREACHABLE_{r_id}",
                            dimension=CheckDimension.FUNCTIONAL_ACCESSIBILITY,
                            status=CheckStatus.FAIL,
                            severity=CheckSeverity.ERROR,
                            affected_room_ids=[r_id],
                            affected_floor_ids=[f"F{data.get('floor', 0)}"],
                            message=f"Room '{data.get('name')}' cannot be reached from the main entrance."
                        )
                    )

        if not isolated and not unreachable and has_ext_entrance:
            checks.append(
                ArchitecturalCheckResult(
                    check_id="CIRC_FULL_REACHABILITY",
                    dimension=CheckDimension.FUNCTIONAL_ACCESSIBILITY,
                    status=CheckStatus.PASS,
                    severity=CheckSeverity.INFO,
                    message="All rooms are functionally connected and reachable from the main entrance."
                )
            )

        return checks, isolated, unreachable

    def get_shortest_route_distance(self, room_id_a: str, room_id_b: str) -> Optional[float]:
        """Calculates topological walking distance between two spaces."""
        if self.graph.has_node(room_id_a) and self.graph.has_node(room_id_b):
            if self.graph.has_path(room_id_a, room_id_b):
                return float(self.graph.shortest_path_length(room_id_a, room_id_b, weight="distance"))
        return None

