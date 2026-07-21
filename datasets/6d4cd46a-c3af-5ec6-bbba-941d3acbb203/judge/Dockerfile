FROM --platform=linux/amd64 426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.base.python:e4670062c1cb

COPY setup_judge.sh /tmp/setup_judge.sh
RUN chmod +x /tmp/setup_judge.sh && /bin/bash /tmp/setup_judge.sh
WORKDIR /home/workspace/oss_abandon
