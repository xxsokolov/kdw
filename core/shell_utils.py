import asyncio

async def run_shell_command(command: str) -> tuple[bool, str]:
    """
    Асинхронно выполняет shell-команду и возвращает ее результат.

    Args:
        command: Команда для выполнения.

    Returns:
        Кортеж, где первый элемент - булево значение успеха (True/False),
        а второй - стандартный вывод или ошибка.
    """
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        return True, stdout.decode().strip()
    else:
        return False, stderr.decode().strip()
