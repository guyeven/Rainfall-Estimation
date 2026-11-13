#!/bin/zsh
# usage: run_all.sh [RUNLIST]   (default runlist.txt; the original batch ran runlist_rest.txt after nf_tight)
cd "${0:A:h}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
PY=${PY:-python}
cat ${1:-runlist.txt} | xargs -P ${NPAR:-6} -L 1 sh -c '$0 -I run_convex.py "$@" > runs/log_$1.txt 2>&1; echo done $1' $PY
echo ALLDONE
