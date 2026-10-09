# Dashboard screenshots — 9 October 2026

These screenshots illustrate the existing local interfaces. They are not new
registered experimental results and do not change frozen simulation/Kubernetes
artifacts. The complete presentation embeds all six captures.

- `maas_input.jpg`: image upload, tier, request deadline and explicit inference action.
- `maas_result.jpg`: actual HTTP 200 image prediction, 98.1 ms client round-trip,
  70.7 ms gateway latency, Gold deadline 200 ms met. A single request provides
  functional evidence, not an accuracy benchmark or a statistical SLA guarantee.
- `research_dashboard.jpg`: archived 30-block / 180-trial comparison, 230,400 outcomes.
- `grafana_overview.jpg`: live target/ready capacity and request counters.
- `grafana_latency.jpg`: live offered/completed rates and histogram mean/p95.
- `grafana_resources.jpg`: serving process CPU/RAM; CPU mode has zero CUDA VRAM.

`CAPTURE_METADATA.json` records URLs, provenance and hashes. The JSON image
outcome is exported from the MaaS UI. A low-rate 24-request connectivity pulse
populated the live graphs; it is illustrative traffic, outside the research
comparison. No controller weights, thresholds, frozen policies or results were
changed. Historical audit banners remain dated evidence, not current counters.
