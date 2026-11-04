"""Distance-vector routing server for CS4470 Programming Assignment 2."""

from __future__ import annotations

import argparse
import math
import socket
import sys
import threading
import time
from dataclasses import dataclass
from typing import TextIO

INFINITY = math.inf


@dataclass(frozen=True)
class Server:
    server_id: int
    ip: str
    port: int


@dataclass
class Route:
    next_hop: int | None
    cost: float


class TopologyError(ValueError):
    pass


def parse_cost(value: str) -> float:
    if value.lower() in {"inf", "infinity"}:
        return INFINITY
    try:
        cost = float(value)
    except ValueError as exc:
        raise TopologyError(f"invalid link cost: {value}") from exc
    if not math.isfinite(cost) or cost < 0 or not cost.is_integer():
        raise TopologyError(f"link cost must be a non-negative integer or inf: {value}")
    return cost


def read_topology(path: str) -> tuple[dict[int, Server], dict[int, float], int]:
    try:
        lines = [line.split() for line in open(path, encoding="utf-8") if line.strip()]
    except OSError as exc:
        raise TopologyError(f"cannot read topology file '{path}': {exc}") from exc
    if len(lines) < 2:
        raise TopologyError("topology must begin with server and neighbor counts")
    try:
        server_count, neighbor_count = int(lines[0][0]), int(lines[1][0])
    except (ValueError, IndexError) as exc:
        raise TopologyError("server and neighbor counts must be integers") from exc
    if len(lines[0]) != 1 or len(lines[1]) != 1 or server_count < 1 or neighbor_count < 0:
        raise TopologyError("invalid server or neighbor count")
    if len(lines) != 2 + server_count + neighbor_count:
        raise TopologyError("topology line count does not match its declared counts")

    servers: dict[int, Server] = {}
    for row in lines[2:2 + server_count]:
        if len(row) != 3:
            raise TopologyError("server entries must be: <id> <ip> <port>")
        try:
            server = Server(int(row[0]), row[1], int(row[2]))
        except ValueError as exc:
            raise TopologyError(f"invalid server entry: {' '.join(row)}") from exc
        if server.server_id in servers or not (1 <= server.port <= 65535):
            raise TopologyError(f"duplicate server ID or invalid port: {server.server_id}")
        servers[server.server_id] = server

    if len(servers) != server_count:
        raise TopologyError("server IDs must be unique")
    local_ids = {s.server_id for s in servers.values() if s.ip in {"127.0.0.1", "localhost"}}
    # The local server is the only server entry using loopback in the sample; for
    # real topologies, its identity is inferred from the neighbor section below.
    costs: dict[int, float] = {}
    for row in lines[2 + server_count:]:
        if len(row) != 3:
            raise TopologyError("link entries must be: <server-id> <neighbor-id> <cost>")
        try:
            owner, neighbor = int(row[0]), int(row[1])
            cost = parse_cost(row[2])
        except ValueError as exc:
            raise TopologyError(f"invalid link entry: {' '.join(row)}") from exc
        if owner not in servers or neighbor not in servers or owner == neighbor:
            raise TopologyError(f"link references invalid server IDs: {' '.join(row)}")
        if neighbor in costs:
            raise TopologyError(f"duplicate neighbor entry for server {neighbor}")
        costs[neighbor] = cost
        local_ids.add(owner)
    if not local_ids:
        raise TopologyError("could not infer local server ID; include a link entry")
    owners = {int(row[0]) for row in lines[2 + server_count:]}
    if len(owners) != 1:
        raise TopologyError("all link entries must use the same local server ID")
    local_id = next(iter(owners))
    if local_id not in servers:
        raise TopologyError("local server ID is missing from the server list")
    return servers, costs, local_id


class DistanceVectorServer:
    """UDP distance-vector process and its interactive command loop."""

    def __init__(self, servers: dict[int, Server], local_id: int,
                 neighbor_costs: dict[int, float], interval: float,
                 output: TextIO = sys.stdout) -> None:
        if interval <= 0:
            raise ValueError("routing update interval must be positive")
        self.servers = servers
        self.local_id = local_id
        self.local = servers[local_id]
        self.interval = interval
        self.output = output
        # Routing table: destination ID -> chosen next hop and total path cost.
        self.routes: dict[int, Route] = {
            server_id: Route(None, 0 if server_id == local_id else INFINITY)
            for server_id in servers
        }
        self.neighbor_costs = dict(neighbor_costs)
        self.neighbor_vectors: dict[int, dict[int, float]] = {}
        self.last_received: dict[int, float] = {}
        self.packet_count = 0
        self.lock = threading.RLock()
        self.running = threading.Event()
        self.sock: socket.socket | None = None

    def log(self, message: str) -> None:
        with self.lock:
            print(message, file=self.output, flush=True)

    def start(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.local.ip, self.local.port))
        now = time.monotonic()
        self.last_received = {neighbor: now for neighbor in self.neighbor_costs}
        self.running.set()
        threading.Thread(target=self._receive_loop, daemon=True).start()
        threading.Thread(target=self._periodic_loop, daemon=True).start()
        self.log(f"Server {self.local_id} listening on {self.local.ip}:{self.local.port}")

    def stop(self) -> None:
        self.running.clear()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _serialize_update(self) -> bytes:
        with self.lock:
            # Update message data: count, sender port, sender IP, then repeated
            # (destination IP, destination port, reserved 0x0, server ID, cost).
            fields = [str(len(self.routes)), str(self.local.port), self.local.ip]
            for server_id in sorted(self.routes):
                server = self.servers[server_id]
                cost = self.routes[server_id].cost
                fields.extend((server.ip, str(server.port), "0x0", str(server_id),
                               "inf" if math.isinf(cost) else str(int(cost))))
            return " ".join(fields).encode("utf-8")

    def send_updates(self) -> None:
        if self.sock is None:
            return
        payload = self._serialize_update()
        with self.lock:
            neighbors = [(sid, self.servers[sid]) for sid, cost in self.neighbor_costs.items()
                         if math.isfinite(cost)]
        for _, neighbor in neighbors:
            try:
                self.sock.sendto(payload, (neighbor.ip, neighbor.port))
            except OSError as exc:
                self.log(f"SEND ERROR {neighbor.server_id}: {exc}")

    def _periodic_loop(self) -> None:
        while self.running.is_set():
            deadline = time.monotonic() + self.interval
            while self.running.is_set() and time.monotonic() < deadline:
                self._expire_neighbors()
                time.sleep(min(0.5, max(0.01, deadline - time.monotonic())))
            if not self.running.is_set():
                break
            self.send_updates()

    def _expire_neighbors(self) -> None:
        now = time.monotonic()
        with self.lock:
            changed = False
            for neighbor in list(self.neighbor_costs):
                last = self.last_received.get(neighbor)
                if last is not None and now - last >= 3 * self.interval:
                    self.neighbor_costs[neighbor] = INFINITY
                    self.neighbor_vectors.pop(neighbor, None)
                    del self.last_received[neighbor]
                    changed = True
                    self.log(f"Neighbor {neighbor} timed out; link cost set to infinity")
            if changed:
                self._recompute_routes()

    def _receive_loop(self) -> None:
        assert self.sock is not None
        while self.running.is_set():
            try:
                data, address = self.sock.recvfrom(65535)
            except OSError:
                break
            try:
                self._handle_packet(data, address)
            except (ValueError, UnicodeDecodeError) as exc:
                self.log(f"IGNORED INVALID UPDATE: {exc}")

    def _handle_packet(self, data: bytes, address: tuple[str, int]) -> None:
        fields = data.decode("utf-8").split()
        if len(fields) < 3:
            raise ValueError("missing message header")
        count, sender_port = int(fields[0]), int(fields[1])
        sender_ip = fields[2]
        if count < 1 or len(fields) != 3 + count * 5:
            raise ValueError("update field count does not match message length")
        sender_ids = [sid for sid, server in self.servers.items()
                      if server.port == sender_port and server.ip == sender_ip]
        if not sender_ids:
            sender_ids = [sid for sid, server in self.servers.items()
                          if server.port == sender_port and server.ip == address[0]]
        if not sender_ids:
            raise ValueError("sender is not listed in this topology")
        sender = sender_ids[0]
        if sender == self.local_id:
            raise ValueError("received own update")

        vector: dict[int, float] = {}
        offset = 3
        for _ in range(count):
            ip, port_text, _reserved, sid_text, cost_text = fields[offset:offset + 5]
            offset += 5
            sid = int(sid_text)
            if sid not in self.servers:
                continue
            expected = self.servers[sid]
            if expected.port != int(port_text) or expected.ip != ip:
                raise ValueError(f"address mismatch for server {sid}")
            vector[sid] = parse_cost(cost_text)
        if self.local_id not in vector:
            raise ValueError("update does not include this server")

        with self.lock:
            if sender not in self.neighbor_costs:
                raise ValueError("update came from a server that is not a configured neighbor")
            self.neighbor_vectors[sender] = vector
            self.last_received[sender] = time.monotonic()
            self.packet_count += 1
            self._recompute_routes()
        self.log(f"RECEIVED A MESSAGE FROM SERVER {sender}")

    def _recompute_routes(self) -> None:
        for destination in self.servers:
            if destination == self.local_id:
                self.routes[destination] = Route(None, 0)
                continue
            best_cost, best_hop = INFINITY, None
            for neighbor, link_cost in self.neighbor_costs.items():
                if not math.isfinite(link_cost):
                    continue
                if neighbor == destination:
                    candidate = link_cost
                else:
                    advertised = self.neighbor_vectors.get(neighbor, {}).get(destination, INFINITY)
                    candidate = link_cost + advertised
                if candidate < best_cost:
                    best_cost, best_hop = candidate, neighbor
            self.routes[destination] = Route(best_hop, best_cost)

    def command(self, line: str) -> bool:
        parts = line.split()
        if not parts:
            return True
        command = parts[0]
        try:
            if command == "display" and len(parts) == 1:
                with self.lock:
                    for sid in sorted(self.routes):
                        route = self.routes[sid]
                        hop = "-" if route.next_hop is None else str(route.next_hop)
                        cost = "inf" if math.isinf(route.cost) else str(int(route.cost))
                        self.log(f"{sid} {hop} {cost}")
                self.log("display SUCCESS")
            elif command == "packets" and len(parts) == 1:
                with self.lock:
                    count = self.packet_count
                    self.packet_count = 0
                self.log(f"{count}\npackets SUCCESS")
            elif command == "step" and len(parts) == 1:
                self.send_updates()
                self.log("step SUCCESS")
            elif command == "update" and len(parts) == 4:
                first, second = int(parts[1]), int(parts[2])
                new_cost = parse_cost(parts[3])
                if self.local_id not in (first, second):
                    raise ValueError("update must specify this server and one neighbor")
                neighbor = second if first == self.local_id else first
                if neighbor not in self.neighbor_costs:
                    raise ValueError(f"server {neighbor} is not a neighbor")
                with self.lock:
                    self.neighbor_costs[neighbor] = new_cost
                    if math.isinf(new_cost):
                        self.neighbor_vectors.pop(neighbor, None)
                        self.last_received.pop(neighbor, None)
                    else:
                        self.last_received[neighbor] = time.monotonic()
                    self._recompute_routes()
                self.log(f"{' '.join(parts)} SUCCESS")
            elif command == "disable" and len(parts) == 2:
                neighbor = int(parts[1])
                if neighbor not in self.neighbor_costs:
                    raise ValueError(f"server {neighbor} is not a neighbor")
                with self.lock:
                    self.neighbor_costs[neighbor] = INFINITY
                    self.neighbor_vectors.pop(neighbor, None)
                    self.last_received.pop(neighbor, None)
                    self._recompute_routes()
                self.log(f"{' '.join(parts)} SUCCESS")
            elif command == "crash" and len(parts) == 1:
                self.stop()
                self.log("crash SUCCESS")
                return False
            else:
                raise ValueError("invalid command or argument count")
        except (ValueError, TopologyError) as exc:
            self.log(f"{' '.join(parts)} ERROR: {exc}")
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Distance-vector routing server")
    parser.add_argument("-t", required=True, metavar="topology-file")
    parser.add_argument("-i", required=True, type=float, metavar="routing-update-interval")
    args = parser.parse_args()
    try:
        servers, costs, local_id = read_topology(args.t)
        server = DistanceVectorServer(servers, local_id, costs, args.i)
        server.start()
    except (TopologyError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

    try:
        for line in sys.stdin:
            if not server.command(line):
                break
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
