# Copyright 2021 The Distla Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =============================================================================
"""
Performs benchmarks of invsqrt. The benchmarks are performed for each
combination of various parameters, specified within `main()` in the case that
this file is the main program. Output is returned as a `DataFrame` and saved as
a `.csv` file to `output_dir_path/output_name`.csv.
In the default case of `output_dir_path=None`, it is taken to be the current
working directory.
"""

import functools
import itertools

import jax
from jax import lax
import jax.numpy as jnp
import numpy as np

from distla_core.analysis import analysis
from distla_core.analysis import analyze_invsqrt
from distla_core.analysis.benchmarks import benchmark_utils


def _invsqrt_tflops(out, in_args, params, per_iter=False):
  """ `speed_function` for `benchmark` estimating the throughput of a invsqrt
  decomposition in TFLOP/s.

  This is estimated as
  `((2 or 8) * 2 * out_rows * out_cols ** 2 + out_rows * out_cols) / dt`, i.e.
  the cost of a Newton-Schulz iteration. If `per_iter` is `True`, the result is
  normalized against the actual number of iterations.
  """
  out_rows, dtype = params[:2]
  dt = out[0]

  if dtype in set([np.complex64, np.complex128, jnp.complex64, jnp.complex128]):
    coef = 8
  else:
    coef = 2
  flops_mmult = 2 * coef * (out_rows ** 3)
  flops = flops_mmult + out_rows ** 2
  result = benchmark_utils.tflops_per_second(flops, dt)
  header = "TFLOPS/s"
  return benchmark_utils.per_iter(per_iter, out[-1], result, header)


def _invsqrt_tflops_per_iter(out, in_args, params):
  return _invsqrt_tflops(out, in_args, params, per_iter=True)


def _invsqrt_gbps(out, in_args, params, per_iter=False):
  """ `speed_function` for `benchmark` estimating the effective bandwidth
  of a invsqrt decomposition in GB/s. The number of elements is estimated as
  2 * the size of the input.
  For a matrix multiplication of dimensions `m, n, k` that took `dt` seconds,
  we define `GB/s := (GB of input + GB of output) / (1E9 * dt)`.
  """
  out_rows, dtype = params[:2]
  dt = out[0]
  n_elements = 2 * (out_rows ** 2)
  result = benchmark_utils.gbps(n_elements, dtype, dt)
  header = "GB/s"
  return benchmark_utils.per_iter(per_iter, out[-1], result, header)


def _invsqrt_gbps_per_iter(out, in_args, params):
  return _invsqrt_gbps(out, in_args, params, per_iter=True)


def benchmark_invsqrt(out_rows, dtypes, p_szs, precisions, seeds, serial, eps,
                      maxiter, s_min_est, s_thresh, s_min, s_max,
                      ev_distribution, batch_size=5, reduction_mode="median",
                      output_dir_path=None, output_name="benchmark_invsqrt"):
  """
  Runs benchmarks of invsqrt. One benchmark per combination of arguments
  is run. Output is saved to `output_dir_path/output_name`.csv, and also
  returned as a `DataFrame`. `output_dir_path` is the current working directory
  if unspecified.

  Args:
    out_rows: rows of the input matrix
    dtypes: dtype of the matrices
    p_szs: panel size of the SUMMA multiplications
    precisions: ASIC matmul precision
    seeds: Random seed to initialize input; system clock if None.
    serial: Whether to run in serial or distributed mode.
    eps: Convergence threshold.
    maxiter: When to terminate if convergence stagnates.
    s_min_est: Estimated lowest eigenvalue; None means machine epsilon;
      -1 means the true value.
    s_thresh: When to switch to Newton-Schulz from `rogue` iterations.
    s_min: Smallest nonzero eigenvalue of the input matrix.
    s_max: Largest eigenvalue of the input matrix.
    ev_distribution: `linear` or `geometric` distribution of eigenvalues in
      the input matrix.
    batch_size: Number of runs to do per benchmark.
    reduction_mode: how to assemblage batches.
    output_dir_path: directory of output; CWD if None
    output_name: output saved to OUTPUT_NAME.csv
  Returns:
    The results as a DataFrame.
  """
  dtypes = tuple([jnp.dtype(d) for d in dtypes])
  params = list(itertools.product(
    out_rows, dtypes, p_szs, precisions, seeds, serial, eps, maxiter,
    s_min_est, s_thresh, s_min, s_max, ev_distribution))

  param_headers = ["N_rows", "dtype", "p_sz", "precision", "seed",
                   "serial", "eps", "maxiter", "s_min_est", "s_thresh",
                   "s_min", "s_max", "ev_distribution"]
  init_f = functools.partial(
    analyze_invsqrt._initialize_invsqrt, return_answer=False
  )
  target_f = analyze_invsqrt._run_invsqrt

  speed_functions = [
    analyze_invsqrt._rogue_iterations,  analyze_invsqrt._total_iterations,
    _invsqrt_tflops, _invsqrt_tflops_per_iter, _invsqrt_gbps,
    _invsqrt_gbps_per_iter]
  return analysis.benchmark(init_f, target_f, params, param_headers,
                            reduction_mode=reduction_mode,
                            batch_size=batch_size,
                            speed_functions=speed_functions,
                            output_dir_path=output_dir_path,
                            output_name=output_name)


def main():
  OUT_ROWS = (1024,)  # rows of the input matrix
  DTYPES = (np.float32,)  # dtype of the matrices
  P_SZS = (128,)  # panel size of the SUMMA multiplications
  PRECISIONS = (lax.Precision.HIGHEST,) # ASIC matmul precision
  SEEDS = (None,)  # Random seed to initialize input; system clock if None.
  SERIAL = (False, True) # Whether to run in serial or distributed mode.
  EPS = (None,) # Convergence threshold.
  MAXITER = (200,) # When to terminate if convergence stagnates.
  S_MIN_EST = (None,) # Estimated lowest eigenvalue;
                      # None means machine epsilon; -1 means the true value.
  S_THRESH = (0.1,) # When to switch to Newton-Schulz from `rogue` iterations.
  S_MIN = (0.1,) # Smallest nonzero eigenvalue of the input matrix.
  S_MAX = (1.0,) # Largest eigenvalue of the input matrix.
  EV_DISTRIBUTION = ("linear",) # `linear` or `geometric` distribution of
                                # eigenvalues in the input matrix.
  BATCH_SIZE = 1 # How many runs to assemblage
  REDUCTION_MODE = "median"  # how to assemblage results
  OUTPUT_DIR_PATH = None  # directory of output; CWD if None
  OUTPUT_NAME = "benchmark_invsqrt" # output saved to OUTPUT_NAME.csv
  _ = benchmark_invsqrt(
    OUT_ROWS, dtypes=DTYPES, p_szs=P_SZS, precisions=PRECISIONS, seeds=SEEDS,
    serial=SERIAL, eps=EPS, maxiter=MAXITER, s_min_est=S_MIN_EST,
    s_thresh=S_THRESH, s_min=S_MIN, s_max=S_MAX,
    ev_distribution=EV_DISTRIBUTION, batch_size=BATCH_SIZE,
    reduction_mode=REDUCTION_MODE, output_dir_path=OUTPUT_DIR_PATH,
    output_name=OUTPUT_NAME)


if __name__ == "__main__":
  main()
