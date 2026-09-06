FROM 426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.base.python:e4670062c1cb

USER root

RUN mkdir -p /home/workspace/scoring/data \
  && mkdir -p /home/workspace/submission

COPY score.py /home/workspace/scoring/score.py
COPY p6zeta_lib.py /home/workspace/scoring/p6zeta_lib.py
COPY perturb_v2.py /home/workspace/scoring/perturb_v2.py
COPY data/ /home/workspace/scoring/data/

WORKDIR /home/workspace
CMD ["/bin/bash", "/home/workspace/scoring/test.sh"]
