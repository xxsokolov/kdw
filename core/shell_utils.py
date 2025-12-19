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
        stdout.decode().strip(),
        stderr.decode().strip()
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
        return 1, ""

    while True:
        line = await process.stdout.readline()
        if not line:
            break

        decoded_line = line.decode().strip()
        full_log += decoded_line + "\n"

        # Чтобы не спамить API Telegram, обновляем сообщение не чаще раза в 2 секунды
        current_time = asyncio.get_event_loop().time()
        if current_time - last_sent_time > 2:
            try:
                await message.edit_text(f"<pre>{full_log}</pre>", parse_mode='HTML')
                last_sent_time = current_time
            except Exception:
                # Игнорируем ошибки, если сообщение не изменилось
                pass
    
    # Отправляем финальный полный лог
    try:
        await message.edit_text(f"<pre>{full_log}</pre>", parse_mode='HTML')
    except Exception:
        pass

    await process.wait()
    return process.returncode, full_log
