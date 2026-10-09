FROM python:3.12.12-slim@sha256:42f1689d6d6b906c7e829f9d9ec38491550344ac9adc01e464ff9a08df1ffb48 AS base
WORKDIR /app
COPY prototype/requirements.txt /app/prototype/requirements.txt
RUN pip install --no-cache-dir -r prototype/requirements.txt
ENV HOST=0.0.0.0 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd -m app
USER app

FROM base AS controller
COPY prototype/kubernetes/observability.py /app/prototype/kubernetes/observability.py
COPY prototype/__init__.py prototype/adapters.py prototype/controller.py prototype/gateway.py prototype/http.py prototype/inference.py prototype/telemetry.py /app/prototype/
COPY joint_routing /app/joint_routing
COPY joint_sla_v2 /app/joint_sla_v2
COPY dynamic_placement /app/dynamic_placement
COPY placement_experiment /app/placement_experiment
CMD ["python", "-m", "prototype.gateway"]

FROM base AS inference_dependencies
USER root
COPY prototype/requirements-inference-lock.txt /app/prototype/requirements-inference-lock.txt
RUN pip install --no-cache-dir -r prototype/requirements-inference-lock.txt
RUN pip install --no-cache-dir --no-deps torch==2.10.0+cpu torchvision==0.25.0+cpu --index-url https://download.pytorch.org/whl/cpu
USER app
ENV TORCH_HOME=/home/app/.cache/torch
RUN python -c "from torchvision.models import mobilenet_v3_large, MobileNet_V3_Large_Weights; mobilenet_v3_large(weights=MobileNet_V3_Large_Weights.IMAGENET1K_V2)"

FROM inference_dependencies AS inference
COPY prototype/__init__.py prototype/adapters.py prototype/controller.py prototype/gateway.py prototype/http.py prototype/inference.py prototype/telemetry.py /app/prototype/
CMD ["python", "-m", "prototype.inference"]
