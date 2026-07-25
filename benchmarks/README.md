# MMLC Runtime benchmarks

`run_release_benchmark.py` measures two deterministic workloads:

- independent arithmetic transactions;
- a linear dependency chain.

The benchmark records median wall-clock time, throughput, peak Python allocation
observed by `tracemalloc`, audit status, and semantic-hash reproducibility.

```bash
python benchmarks/run_release_benchmark.py \
  --sizes 64 256 1024 \
  --repeats 3 \
  --output release/benchmark_v1.0.json
```

These are implementation measurements on one machine. They are not evidence that
MMLC is faster than spreadsheets, DAG runtimes, databases, symbolic systems, or
probabilistic programming tools.
