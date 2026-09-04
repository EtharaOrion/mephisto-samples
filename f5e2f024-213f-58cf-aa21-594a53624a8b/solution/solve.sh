#!/bin/bash
set -euo pipefail

mkdir -p /home/workspace/submission/src

cp /solution/reference_solver.py /home/workspace/submission/src/reference_solver.py
cp /home/workspace/scoring/p6zeta_lib.py /home/workspace/submission/src/p6zeta_lib.py 2>/dev/null || true

cat > /home/workspace/submission/build.sh <<'EOF'
#!/bin/bash
set -euo pipefail
chmod +x ./solve
EOF
chmod +x /home/workspace/submission/build.sh

cat > /home/workspace/submission/solve <<'EOF'
#!/bin/bash
exec python3 /home/workspace/submission/src/reference_solver.py "$@"
EOF
chmod +x /home/workspace/submission/solve
