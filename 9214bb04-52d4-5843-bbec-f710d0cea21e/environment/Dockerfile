FROM 426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.base.python:e4670062c1cb
USER root
RUN mkdir -p /home/workspace/data /home/workspace/submission && \
    chown -R agent:agent /home/workspace
COPY --chown=agent:agent p3gamma_lib.py /home/workspace/p3gamma_lib.py
COPY --chown=agent:agent README.md /home/workspace/README.md
COPY --chown=agent:agent data/universe_p3gamma_2026.csv /home/workspace/data/universe_p3gamma_2026.csv
COPY --chown=agent:agent data/sec_xbrl_panel_stripped.csv /home/workspace/data/sec_xbrl_panel_stripped.csv
COPY --chown=agent:agent data/sec_sector_taxonomy.csv /home/workspace/data/sec_sector_taxonomy.csv
COPY --chown=agent:agent data/regulatory_text_bundle.tar.gz /home/workspace/data/regulatory_text_bundle.tar.gz
USER agent
WORKDIR /home/workspace
CMD ["/bin/bash"]
