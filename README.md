# CS4470 Programming Assignment 2

Python implementation of the distance-vector routing assignment. The assignment PDF remains the source of truth for protocol behavior and submission requirements.

## Requirements

- Python 3.10 or newer
- No third-party packages are required

## Project files

- `dv.py` — UDP server, distance-vector routing table, and interactive command loop.
- `topology.example.txt` — topology format example for server 1.
- `topology-1.txt` through `topology-4.txt` — ready-to-run loopback topologies for four servers.
- `project2.pdf` — assignment specification.

## Topology file format

Each router reads its own topology file. Use one item per line:

1. Number of servers
2. Number of neighbors
3. One `<server-ID> <server-IP> <server-port>` line per server
4. One `<server-ID> <neighbor-ID> <link-cost>` line per neighbor link

Use actual reachable machine IP addresses and ports when running across multiple machines. The included topologies use loopback and are for running all four servers on one machine.

## Running

Pass the topology filename and routing update interval as arguments. For example:

```powershell
python .\dv.py -t .\topology-1.txt -i 5
```

To run the included four-server example on Windows, open four separate PowerShell terminals in the project folder and run one command in each:

```powershell
python .\dv.py -t .\topology-1.txt -i 5
python .\dv.py -t .\topology-2.txt -i 5
python .\dv.py -t .\topology-3.txt -i 5
python .\dv.py -t .\topology-4.txt -i 5
```

If needed, replace `python` with the full path to your Python executable. Each server reads only its own topology file, and the four files use ports 4091–4094. Start each server only once: if a port is already in use, that server is likely already running. Enter `crash` in its terminal (or press Ctrl+C) before restarting it. A server will report neighbor timeouts if the corresponding neighbor processes are not running.

For a different network, create one topology file per server, changing the neighbor count and link entries to match that server's links. Configure each server's reachable IP address and a unique UDP port in every file.

Interactive commands supported by `dv.py`: `update <id1> <id2> <cost|inf>`, `step`, `packets`, `display`, `disable <server-ID>`, and `crash`.
