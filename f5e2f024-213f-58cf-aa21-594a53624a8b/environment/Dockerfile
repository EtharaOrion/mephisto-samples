FROM 426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.base.python:e4670062c1cb

USER root

RUN mkdir -p /home/workspace/p6zeta/data \
  && chown -R agent:agent /home/workspace/p6zeta

COPY --chown=agent:agent p6zeta_lib.py /home/workspace/p6zeta/p6zeta_lib.py
COPY --chown=agent:agent README.md /home/workspace/p6zeta/README.md
COPY --chown=agent:agent task_instruction.md /home/workspace/task_instruction.md
COPY --chown=agent:agent data/ /home/workspace/p6zeta/data/

USER agent
WORKDIR /home/workspace/p6zeta
CMD ["/bin/bash"]
