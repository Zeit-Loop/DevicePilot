FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/data/huggingface

WORKDIR /app

RUN addgroup --system --gid 10001 app && \
    adduser --system --uid 10001 --ingroup app app && \
    mkdir -p /data/huggingface && \
    chown -R 10001:10001 /data

COPY requirements.txt constraints-docker.txt ./
RUN python -m pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch==2.13.0+cpu" \
    && python -m pip install --no-cache-dir \
        --constraint constraints-docker.txt -r requirements.txt \
    && python -c "import torch; assert torch.__version__ == '2.13.0+cpu'; assert torch.version.cuda is None; assert not torch.cuda.is_available()" \
    && python -c "import importlib.metadata as m; names={d.metadata['Name'].lower() for d in m.distributions() if d.metadata['Name']}; forbidden=[n for n in names if n == 'cuda-toolkit' or n == 'triton' or n.startswith('cuda-') or n.startswith('nvidia-')]; assert not forbidden, forbidden" \
    && python -m pip check

COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 scripts ./scripts
COPY --chown=10001:10001 knowledge ./knowledge

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
