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
        stdout.decode('utf-8', errors='replace').strip(),
        stderr.decode('utf-8', errors='replace').strip()
    )

async def run_command_streamed(command: str, update, context, message, stdin_input: bytes = None):
    """
    Выполняет команду, опционально передавая ей данные в stdin,
    и стримит ее вывод в Telegram сообщение.
    """
    process = await asyncio.create_subprocess_shell(
        command,
        stdin=asyncio.subprocess.PIPE if stdin_input else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT  # Объединяем stdout и stderr
    )

    # Асинхронно передаем данные в stdin и закрываем его
    if stdin_input and process.stdin:
        try:
            process.stdin.write(stdin_input)
            await process.stdin.drain()
        finally:
            process.stdin.close()

    full_log = ""
    last_sent_time = 0
    
    if process.stdout is None:
        await process.wait()
        return process.returncode, ""

    while True:
        line = await process.stdout.readline()
        if not line:
            break

        decoded_line = line.decode('utf-8', errors='replace').strip()
        full_log += decoded_line + "\n"

        current_time = asyncio.get_event_loop().time()
        if current_time - last_sent_time > 2:
            try:
                # Стримим промежуточный лог
                await message.edit_text(f"<pre>{full_log}</pre>", parse_mode='HTML')
                last_sent_time = current_time
            except Exception:
                pass

    await process.wait()
    return process.returncode, full_log
