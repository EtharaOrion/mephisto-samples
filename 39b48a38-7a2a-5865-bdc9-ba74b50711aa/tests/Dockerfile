# Verifier image. Carries the reference codec, the sealed-seed column generator, the isolated
# runner and the scorer. None of these bytes exist in the agent image.
FROM python:3.11-slim@sha256:90744cff8f32887f075c47d747a173ff333e9e98801667af93c357fa9f5e28ff

RUN pip install --no-cache-dir pytest==8.3.4

WORKDIR /home/workspace

COPY harness/ /home/workspace/tests/harness/
COPY grading.json /home/workspace/tests/grading.json
COPY lanes.py /home/workspace/tests/lanes.py
COPY score.py /home/workspace/tests/score.py
COPY test_output.py /home/workspace/tests/test_output.py
COPY test.sh /home/workspace/tests/test.sh

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENTRYPOINT []
CMD ["bash", "/home/workspace/tests/test.sh"]
