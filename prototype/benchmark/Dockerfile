ARG GATEWAY_IMAGE
ARG INFERENCE_IMAGE
FROM ${GATEWAY_IMAGE} AS gateway
COPY prototype/benchmark /app/prototype/benchmark
CMD ["python", "-m", "prototype.benchmark.gateway_runtime"]
FROM ${INFERENCE_IMAGE} AS inference
COPY prototype/benchmark /app/prototype/benchmark
CMD ["python", "-m", "prototype.benchmark.inference"]
