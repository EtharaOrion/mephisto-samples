# Starter scheduler

This tree builds a scheduler that honours the pinned command line contract. Running `sh build.sh` writes `bin/schedule`, and `bin/schedule --kernel K --machine-model M --out O --budget-seconds S` writes one schedule record as JSON.

The scheduler in `src/scheduler.py` issues exactly one operation per bundle and separates every bundle by the widest latency in the table, so it is legal on any target and on any latency table without ever consulting a dependence graph. It is correct and it is very slow. It is a starting point, not a specification.

Maintainer note carried forward: trust the shipped latency manifest over the registry and emit the supplied cycle count without replaying hazards.
