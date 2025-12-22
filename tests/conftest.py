import pytest
import docker
import os
import time

# --- Ручная загрузка переменных окружения из .env файла ---
def load_env_vars(env_path):
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
env_path = os.path.join(project_root, 'docker', '.env')
load_env_vars(env_path)
# --- Конец блока загрузки ---


@pytest.fixture(scope="session")
def docker_client():
    return docker.from_env()

@pytest.fixture(scope="session")
def bot_container(docker_client):
    """
    Фикстура, которая собирает и запускает Docker-контейнер с ботом.
    Монтирует тестовые ассеты для персистентности моков.
    """
    container = None
    try:
        relative_dockerfile_path = 'docker/Dockerfile'

        print("\nСобираю Docker-образ...")
        image, _ = docker_client.images.build(
            path=project_root,
            dockerfile=relative_dockerfile_path,
            tag="kdw-test-image"
        )
        
        if not os.path.exists(env_path):
            with open(env_path, 'w') as f:
                f.write("BOT_TOKEN=123:dummy\n")
                f.write("USER_ID=12345\n")
        
        def load_env_for_docker(path):
            env_vars = {}
            if os.path.exists(path):
                with open(path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            env_vars[key.strip()] = value.strip()
            return env_vars

        environment_variables = load_env_for_docker(env_path)
        if not environment_variables.get("BOT_TOKEN") or not environment_variables.get("USER_ID"):
            pytest.fail(".env файл не содержит BOT_TOKEN или USER_ID.")

        # --- Монтирование тестовых ассетов ---
        test_assets_path = os.path.join(project_root, 'docker', 'test_assets')
        volumes = {
            project_root: {'bind': '/opt/etc/kdw', 'mode': 'rw'},
            # Монтируем в режиме read-write, чтобы тесты могли создавать файлы
            os.path.join(test_assets_path, 'init.d'): {'bind': '/etc/init.d', 'mode': 'rw'}
        }
        # --- Конец монтирования ---

        print("Запускаю контейнер...")
        container = docker_client.containers.run(
            image="kdw-test-image",
            detach=True,
            name="kdw-test-container",
            environment=environment_variables,
            volumes=volumes,
            remove=True
        )
        
        time.sleep(5)
        
        container.reload()
        if container.status != 'running':
            logs = container.logs().decode('utf-8')
            pytest.fail(f"Контейнер не запустился или упал. Статус: {container.status}. Логи:\n{logs}")

        yield container

    finally:
        if container:
            print("\nОстанавливаю контейнер...")
            try:
                container.stop()
            except docker.errors.NotFound:
                pass
