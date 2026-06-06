import docker
from docker.errors import DockerException

_client = None


def get_client():
    global _client
    if _client is None:
        try:
            _client = docker.from_env()
            _client.ping()
        except DockerException as e:
            raise SystemExit(
                f"[red]Error:[/red] Cannot connect to Docker daemon.\n"
                f"  Is Docker installed and running?\n  {e}"
            )
    return _client
