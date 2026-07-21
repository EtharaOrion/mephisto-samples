FROM --platform=linux/amd64 426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.base.python:e4670062c1cb

COPY setup_workspace.sh /tmp/setup_workspace.sh
RUN chmod +x /tmp/setup_workspace.sh && /bin/bash /tmp/setup_workspace.sh \
    && chown -R agent:agent /home/workspace/enforcement
USER agent
WORKDIR /home/workspace/enforcement
