# CS4470 Programming Assignment 2

Starter project for the distance-vector routing assignment. The assignment PDF is the source of truth for protocol behavior and submission requirements.

## Requirements

- Python 3.10 or newer
- No third-party packages are needed for the starter scaffold

## Project files

- `dv.py` — required program entry point; implementation has not been started.
- `topology.example.txt` — format example for one router's local topology file.
- `project2.pdf` — assignment specification.

## Topology file format

Each router reads its own topology file. Use one item per line:

1. Number of servers
2. Number of neighbors
3. One `<server-ID> <server-IP> <server-port>` line per server
4. One `<server-ID> <neighbor-ID> <link-cost>` line per neighbor link

Use actual reachable machine IP addresses and ports when running across multiple machines. The example uses loopback and is only a format/sample configuration.

## Running

The required command-line form is:

```text
python dv.py -t <topology-file> -i <routing-update-interval>
```

For example, after the server implementation is added:

```text
python dv.py -t topology.example.txt -i 5
```

The server and interactive commands described in `project2.pdf` are not implemented in this starter setup.
