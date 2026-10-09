"""Explicit single-request demo of the existing local Kubernetes inference API."""
import base64
import io
import json
import time
from urllib import error, request

GATEWAY = 'http://127.0.0.1:8091'
MAX_IMAGE_BYTES = 1_000_000


def payload(tier, deadline_ms, image=None, seed=0):
    """Validate an image before submitting it; never change runtime policies."""
    if tier not in ('Gold', 'Silver', 'Bronze'):
        raise ValueError('Unknown tier')
    if not 0 < float(deadline_ms) <= 60_000:
        raise ValueError('Deadline must be between 0 and 60000 ms')
    body = {'tier': tier, 'deadline_ms': float(deadline_ms)}
    if image is not None:
        from PIL import Image
        if not image or len(image) > MAX_IMAGE_BYTES:
            raise ValueError('Use an image no larger than 1 MB.')
        with Image.open(io.BytesIO(image)) as decoded:
            if decoded.format not in ('JPEG', 'PNG') or decoded.width * decoded.height > 16_000_000:
                raise ValueError('Use a JPEG/PNG image with at most 16 million pixels.')
            decoded.verify()
        body['image_base64'] = base64.b64encode(image).decode('ascii')
    else:
        if type(seed) is not int or not 0 <= seed < 2**31:
            raise ValueError('Invalid benchmark seed')
        body['seed'] = seed
    return body


def infer(body):
    """Send exactly one request, including HTTP rejections in the outcome."""
    started = time.perf_counter()
    req = request.Request(GATEWAY + '/infer', data=json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
    try:
        response = request.urlopen(req, timeout=65)
    except error.HTTPError as failure:
        response = failure
    with response:
        status = response.code
        raw = response.read(2_000_001)
    elapsed = (time.perf_counter() - started) * 1000
    if len(raw) > 2_000_000:
        raise ValueError('Inference response too large')
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        result = {'error': f'Gateway returned HTTP {status} without a JSON response'}
    if not isinstance(result, dict):
        raise ValueError('Expected a JSON object from the gateway')
    return {'http_status': status, 'client_latency_ms': elapsed,
            'client_sla_failure': status != 200 or elapsed > body['deadline_ms'],
            'tier': body['tier'], 'deadline_ms': body['deadline_ms'], 'response': result}


def render():
    import pandas as pd
    import streamlit as st
    st.title('AI Inference / MaaS Demo')
    st.write('Model as a Service: submit an image to the real pretrained model through the JointSLA Kubernetes gateway.')
    st.caption('Client → JointSLA gateway → ready PyTorch pod → prediction. This is a live demo, separate from frozen experiments.')
    st.link_button('Open live Grafana', 'http://127.0.0.1:3001/d/jointsla-runtime')
    with st.form('maas_request'):
        mode = st.radio('Input', ['Image classification', 'Synthetic tensor · connectivity demo'])
        uploaded = st.file_uploader('Upload JPEG / PNG (maximum 1 MB)', type=['jpg', 'jpeg', 'png'], max_upload_size=1)
        cols = st.columns(3)
        tier = cols[0].selectbox('Request tier', ['Gold', 'Silver', 'Bronze'])
        deadline = cols[1].number_input('Request SLA deadline (ms)', min_value=1, max_value=60_000, value=200)
        seed = cols[2].number_input('Synthetic input seed', min_value=0, max_value=2**31-1, value=0)
        submitted = st.form_submit_button('Run real inference', type='primary')
    st.caption('One click sends one request. No retries or background load. Demo requests appear in live telemetry and can affect the existing autoscaler; controller parameters stay unchanged.')
    st.caption('The request deadline affects routing and outcome classification. The scaler retains its existing configured control deadline.')
    if submitted:
        st.session_state.pop('maas_outcome', None)
        try:
            if mode == 'Image classification' and uploaded is None:
                raise ValueError('Upload an image, or select the synthetic connectivity demo.')
            image = uploaded.getvalue() if mode == 'Image classification' else None
            body = payload(tier, deadline, image=image, seed=int(seed))
            if image is not None:
                st.image(image, caption='Submitted image', width=300)
            with st.spinner('Executing the real model through JointSLA…'):
                st.session_state['maas_outcome'] = infer(body)
        except (OSError, ValueError) as failure:
            st.error(f'Request could not complete: {failure}. Check Docker/Kubernetes and gateway port 8091. No retry was sent.')
    outcome = st.session_state.get('maas_outcome')
    if outcome:
        result = outcome['response']
        cols = st.columns(4)
        cols[0].metric('HTTP status', outcome['http_status'])
        cols[1].metric('Client round-trip', f"{outcome['client_latency_ms']:.1f} ms")
        cols[2].metric('Gateway latency', f"{result['gateway_latency_ms']:.1f} ms" if 'gateway_latency_ms' in result else 'Unavailable')
        cols[3].metric('Client SLA outcome', 'FAILURE' if outcome['client_sla_failure'] else 'MET')
        st.caption(f"Last request: {outcome['tier']} · deadline {outcome['deadline_ms']:g} ms. Client latency includes HTTP transport; gateway latency is measured inside the gateway.")
        if outcome['http_status'] != 200:
            st.error(result.get('error', 'Inference failed or was rejected'))
        else:
            st.write(f"Input: {result.get('input_kind', 'unknown')} · Device: {result.get('device', 'unknown')} · Pretrained: {result.get('pretrained', 'unknown')}")
            if result.get('input_kind') == 'synthetic benchmark tensor':
                st.info('The neural network executes for real, but random tensor predictions have no meaningful image classification interpretation.')
            predictions = pd.DataFrame(result.get('predictions', []))
            if not predictions.empty:
                predictions['confidence_percent'] = predictions['score'] * 100
                st.subheader('Top predictions')
                st.dataframe(predictions[['label', 'class_id', 'confidence_percent']], hide_index=True, width='stretch')
                st.bar_chart(predictions.set_index('label')['confidence_percent'])
            cols = st.columns(2)
            cols[0].metric('Queue time', f"{result['queue_ms']:.1f} ms" if 'queue_ms' in result else 'Unavailable')
            cols[1].metric('Model execution', f"{result['execution_ms']:.1f} ms" if 'execution_ms' in result else 'Unavailable')
            st.caption('ImageNet top-class scores are model outputs, not calibrated correctness guarantees. This demo does not evaluate model accuracy.')
        with st.expander('Full request outcome / routed pod'):
            st.json(outcome)
        st.download_button('Download this outcome (JSON)', json.dumps(outcome, indent=2), 'jointsla_maas_demo_outcome.json', 'application/json')
