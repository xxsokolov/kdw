import asyncio

async def run_command(command: str):
    """
    Асинхронно выполняет shell-команду и возвращает ее код завершения,
    stdout и stderr.
    """
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    return (
        process.returncode,
        stdout.decode('utf-8', errors='replace').strip(), # Добавлено errors='replace'
        stderr.decode('utf-8', errors='replace').strip()  # Добавлено errors='replace'
    )

async def run_command_streamed(command: str, update, context, message):
    """
    Выполняет команду и стримит ее вывод в Telegram сообщение.
    """
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT  # Объединяем stdout и stderr
    )

    full_log = ""
    last_sent_time = 0
    
    if process.stdout is None:
        await process.wait()
        return process.returncode, ""

    while True:
        line = await process.stdout.readline()
        if not line:
            break

        decoded_line = line.decode('utf-8', errors='replace').strip() # Добавлено errors='replace'
        full_log += decoded_line + "\n"

        current_time = asyncio.get_event_loop().time()
        if current_time - last_sent_time > 2:
            try:
                # Стримим промежуточный лог
                await message.edit_text(f"<pre>{full_log}</pre>", parse_mode='HTML')
                last_sent_time = current_time
            except Exception:
                pass
    
    # УДАЛЕНО: Финальное обновление сообщения из run_command_streamed.
    # Теперь это ответственность вызывающей функции (installer.py).

    await process.wait()
    return process.returncode, full_log
