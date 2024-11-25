
FROM thehale/python-poetry:1.8.2-py3.10-slim

COPY . /app
WORKDIR /app

RUN apt-get update
RUN poetry install

EXPOSE 9090

# Run the application
CMD ["poetry", "run", "python", "-m", "surfpizza.server"]
