from pathlib import Path

def generate_dockerfile(project_name: str, python_version: str = "3.12") -> str:
    return f"""FROM python:{python_version}-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
"""

def generate_docker_compose(project_name: str) -> str:
    return f"""version: '3.8'

services:
  web:
    build: .
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    environment:
      - DEBUG=1
    command: python manage.py runserver 0.0.0.0:8000
"""

def save_docker_configs(root_path: Path, project_name: str):
    (root_path / "Dockerfile").write_text(generate_dockerfile(project_name))
    (root_path / "docker-compose.yml").write_text(generate_docker_compose(project_name))

def get_gunicorn_command(project_name: str, workers: int = 3, port: int = 8000) -> str:
    return f"gunicorn {project_name}.wsgi:application --workers {workers} --bind 0.0.0.0:{port}"

def get_uvicorn_command(project_name: str, port: int = 8000) -> str:
    return f"uvicorn {project_name}.asgi:application --host 0.0.0.0 --port {port}"
