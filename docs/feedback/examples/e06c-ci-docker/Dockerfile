FROM debian:12
ARG JQ_VERSION=1.6
ARG YQ_VERSION=4.40.5
RUN curl -fsSL -o /usr/bin/jq https://github.com/jqlang/jq/releases/download/jq-${JQ_VERSION}/jq-linux-amd64
RUN curl -fsSL -o /usr/bin/yq https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/yq_linux_amd64
RUN pip install pyyaml==5.3 \
    six==1.15.0
