
# FROM thehale/python-poetry:1.8.2-py3.10-slim
FROM pfeiffermax/python-poetry:1.12.0-poetry1.8.4-python3.11.10-bookworm

COPY . /app
WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libssl-dev \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && export PATH="$HOME/.cargo/bin:$PATH"
ENV PATH="/root/.cargo/bin:${PATH}"

RUN poetry install

EXPOSE 9090

# Run the application
CMD ["poetry", "run", "python", "-m", "surfpizza.server"]
