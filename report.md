# CS4470 Programming Assignment 2 - Implementation Report

## Overview

`dv.py` implements a distance-vector routing server over UDP. Each process reads its own topology file, binds to the IP address and port assigned to its server ID, and maintains a route for every server listed in that topology. It sends routing updates only on the configured periodic interval or when the user enters `step`.

## Data structures

The routing table is `self.routes`, a dictionary keyed by destination server ID. Each value is a `Route` containing the selected next-hop ID and total path cost. Its declaration is in `dv.py` line 119. The server keeps each directly configured link cost separately in `self.neighbor_costs` and the last distance vector received from each neighbor in `self.neighbor_vectors`.

The UDP update payload is assembled in `_serialize_update` (`dv.py`, documented at line 159). It contains the number of route entries, sender port and IP, then one five-field record per destination: destination IP, port, reserved `0x0`, server ID, and advertised cost. The payload uses whitespace-separated UTF-8 text. Infinite costs are sent as `inf`.

## Routing behavior

For each destination, the server selects the neighbor that minimizes its direct link cost plus that neighbor's advertised cost. Direct-neighbor routes use the configured link cost, and the route to the local server has cost zero. Neighbor update timestamps are monitored; after three consecutive update intervals without a packet, the link is marked infinite and the table is recalculated. A timed-out neighbor can rejoin when it sends an update. Administratively disabled links remain disabled until explicitly re-enabled with `update`.

## Commands

The server supports `update <id1> <id2> <cost|inf>`, `step`, `packets`, `display`, `disable <server-ID>`, and `crash`. `display` sorts rows by destination ID. `packets` reports and resets the count of accepted distance-vector messages since its previous invocation. Successful commands print the required `SUCCESS` response, and received updates print the sender ID.

## Running the sample

Run each included topology in its own terminal, using the commands documented in `README.md`. The sample uses four localhost ports and is intended only for a same-machine demonstration. For multiple machines, replace the loopback addresses with reachable IP addresses in every topology file.

