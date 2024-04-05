ARG BASE_IMAGE=python:3.11-slim
FROM $BASE_IMAGE AS builder

# Set a non-interactive frontend to avoid any interactive prompts during the build
ARG DEBIAN_FRONTEND=noninteractive

# Create directory to copy files to
RUN mkdir -p /source/ /opt/filetao/
WORKDIR /source

# Install dependencies first, so source code changes don't invalidate the build cache
COPY requirements.txt /source/
RUN --mount=type=cache,target=/root/.cache/ \
 python -m pip install --prefix=/opt/filetao -r requirements.txt

COPY ./README.md ./setup.py ./requirements-dev.txt /source/
COPY ./neurons /source/neurons
COPY ./storage /source/storage
RUN python -m pip install --prefix=/opt/filetao --no-deps .

# symlink lib/pythonVERSION to lib/python so path doesn't need to be hardcoded
RUN ln -rs /opt/filetao/lib/python* /opt/filetao/lib/python
COPY ./bin /opt/filetao/bin
COPY ./scripts /opt/filetao/scripts

FROM $BASE_IMAGE AS filetao

RUN mkdir -p ~/.bittensor/wallets && \
    mkdir -p /etc/redis/

COPY --from=builder /opt/filetao /opt/filetao

ENV PATH="/opt/filetao/bin:${PATH}"
ENV LD_LIBRARY_PATH="/opt/filetao/lib:${LD_LIBRARY_PATH}"
ENV REBALANCE_SCRIPT_PATH=/opt/filetao/scripts/rebalance_deregistration.sh
ENV PYTHONPATH="/opt/filetao/lib/python/site-packages/:${PYTHONPATH}"

CMD ["sh", "-c", "filetao run ${FILETAO_NODE} \
    --wallet.name ${FILETAO_WALLET} \
    --wallet.hotkey ${FILETAO_HOTKEY} \
    --netuid ${FILETAO_NETUID:-21} \
    $([ -n \"${FILETAO_IP}\" ] && echo \"--axon.ip ${FILETAO_IP}\") \
    --axon.port ${FILETAO_EXTERNAL_PORT} \
    --axon.external_port ${FILETAO_EXTERNAL_PORT} \
    --subtensor.network ${FILETAO_SUBTENSOR} \
    --database.host ${REDIS_HOST:-127.0.0.1} \
    --database.port ${REDIS_PORT} \
    --database.redis_password ${REDIS_PASSWORD} \
    ${FILETAO_EXTRA_OPTIONS}"]
