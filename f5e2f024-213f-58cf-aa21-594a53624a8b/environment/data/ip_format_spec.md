# 0-1 IP Instance Format Specification

Each instance file is a UTF-8 JSON document with the fields listed below. All fields are required. Additional fields are permitted only under the reserved key `comment`.

## Instance schema

- `instance_id` (string): unique identifier of the form `p6zeta__<split>__<family>__<index>`.
- `family` (string): one of `set-cover`, `zero-one-knapsack`, `graph-coloring-ip`, `tsp-cutting-plane-ip`, `generalized-assignment`, `capacitated-facility-location`, `multi-dimensional-knapsack`.
- `n_vars` (int): number of binary decision variables. Positive.
- `objective_sense` (string): `max` or `min`.
- `objective_coefficients` (list of floats): length `n_vars`.
- `constraints` (list of objects): non-empty. Each element has:
  - `coefficients` (list of floats): length `n_vars`.
  - `rhs` (float): right-hand-side scalar.
  - `sense` (string): one of `<=`, `>=`, `==`.

## Output schema

- `instance_id` (string): echoed from input.
- `status` (string): one of `optimal`, `feasible`, `infeasible`, `unknown`.
- `variables` (list of 0/1 ints or null): length `n_vars` when status is `optimal` or `feasible`; may be null when `infeasible`/`unknown`.
- `objective_value` (float or null): value of the objective at the reported `variables`; may be null when status is `infeasible`/`unknown`.

## Feasibility semantics

For each constraint row, evaluate the dot product `dot = sum(c_i * x_i)`. The row is satisfied iff:

- `sense == '<='` and `dot <= rhs + 1e-9`, or
- `sense == '>='` and `dot >= rhs - 1e-9`, or
- `sense == '=='` and `abs(dot - rhs) <= 1e-9`.

A solution with a reported `status` of `optimal` or `feasible` must satisfy every constraint under this tolerance and every variable must be exactly 0 or 1.
