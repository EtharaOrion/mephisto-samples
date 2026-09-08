FROM 426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.base.python:e4670062c1cb
USER root
RUN mkdir -p /home/workspace/scoring/data /home/workspace/submission
COPY score.py /home/workspace/scoring/score.py
COPY p3gamma_lib.py /home/workspace/scoring/p3gamma_lib.py
COPY data/hidden_opmargin_change_realized.csv /home/workspace/scoring/data/hidden_opmargin_change_realized.csv
COPY data/hidden_sibling_ranks.csv /home/workspace/scoring/data/hidden_sibling_ranks.csv
WORKDIR /home/workspace
CMD ["python3", "/home/workspace/scoring/score.py"]
