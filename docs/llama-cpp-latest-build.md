# Building Latest llama.cpp

This repo expects a recent `llama.cpp` build when using newer serving features such as Qwen3.6 MTP with `draft-mtp`.

The local checkout is expected to live next to this repo:

```text
../llama.cpp
```

## Update And Build

From this repo:

```bash
cd ../llama.cpp
git fetch origin
git rebase origin/master

cmake -S . -B build -DBUILD_SHARED_LIBS=OFF
cmake --build build --config Release -j --target llama-server llama-cli
```

The upstream branch for this checkout is `origin/master`. Do not assume `origin/main` exists for `llama.cpp`.

On Apple Silicon, the default CMake configuration should include the Metal backend. Confirm that in the CMake output before relying on GPU offload.

## Verify MTP Support

After building, verify the server binary and MTP flags:

```bash
build/bin/llama-server --version
build/bin/llama-server --help | rg -i -e "--spec-type|draft-mtp|--spec-draft-n-max"
```

Expected signal:

```text
--spec-draft-n-max N
--spec-type none,draft-simple,draft-eagle3,draft-mtp,ngram-simple,ngram-map-k,ngram-map-k4v,ngram-mod,ngram-cache
```

If `draft-mtp` is missing, the binary is too old for Qwen3.6 MTP serving.

## Use From lm-based

When starting a local model from this repo, point `LLAMA_SERVER_BIN` at the rebuilt binary:

```bash
LLAMA_SERVER_BIN=../llama.cpp/build/bin/llama-server \
MODEL_SLUG=qwen36-27b-mtp-ud-q5k-xl \
ENABLE_RUN_CAPTURE=false \
./run-server.py
```

Use `ENABLE_RUN_CAPTURE=false` for manual bring-up when you do not want to create a new `runs/` directory.

## Qwen3.6 MTP Notes

The Qwen3.6 MTP sidecar uses:

```text
--spec-type draft-mtp
--spec-draft-n-max 4
--ctx-size 262144
```

The native context length is `262144` tokens. Keep `--parallel 1` for MTP; upstream llama.cpp guidance notes that multiple parallel slots are not supported with MTP yet.

## PATH Check

If `llama-server` on `PATH` is older than the freshly built binary, either set `LLAMA_SERVER_BIN` as shown above or update the PATH-installed binary intentionally.

Check both:

```bash
which llama-server
llama-server --version
../llama.cpp/build/bin/llama-server --version
```
