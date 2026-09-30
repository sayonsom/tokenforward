# Clean, isolated benchmark box: no global plugins leak into the vibe/speckit arms.
# Build:  docker build -t tokenforward-bench .
# Run:    docker run --rm -e ANTHROPIC_API_KEY -v "$PWD/bench/results:/app/bench/results" tokenforward-bench \
#           --arms vibe,speckit,tfd --model sonnet --budget 250k
# (Claude subscription instead of API key: run `claude setup-token` on the host, pass -e CLAUDE_CODE_OAUTH_TOKEN)
FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g @anthropic-ai/claude-code

RUN useradd -m bench
USER bench
ENV PATH="/home/bench/.local/bin:${PATH}"
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
 && uv tool install specify-cli \
 && uv tool install graphifyy

# Test env for the brownfield target (httpx pinned) so scoring is identical for every arm.
RUN git clone -q https://github.com/encode/httpx.git /home/bench/httpx-src \
 && cd /home/bench/httpx-src && git checkout -q b5addb64f0161ff6bfe94c124ef76f6a1fba5254 \
 && uv venv -q /home/bench/venv \
 && VIRTUAL_ENV=/home/bench/venv uv pip install -q -r requirements.txt

WORKDIR /app
COPY --chown=bench . /app
ENTRYPOINT ["python3", "bench/run_bench.py", "--python", "/home/bench/venv/bin/python", "--work", "/home/bench/work"]
