# Model Metadata

This directory stores sidecar metadata for local model artifacts in this workspace.

Each local model should have a matching `.json` file named after the artifact, for example:

- `Qwen3.5-35B-A3B-Q4_K_M.gguf`
- `models/Qwen3.5-35B-A3B-Q4_K_M.gguf.json`

Suggested fields:

- `model.slug`: short stable selector used by tooling
- `local_path`: exact local artifact path
- `sha256`: checksum of the local file
- `source`: canonical and GGUF source links
- `download`: machine-readable download source for fetching the artifact again
- `provenance`: how the file was obtained and how confident we are
- `launcher`: intended profile and serving defaults
- `notes`: operational notes that are specific to this artifact

Keep the sidecars conservative. If provenance is inferred or user-reported, say so directly.
