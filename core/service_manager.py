from .shell_utils import run_command

# Имена init-скриптов для служб
SERVICE_NAMES = {
    "shadowsocks": "S22shadowsocks",
    "trojan": "S22trojan",
    "vmess": "S24v2ray", # v2ray обслуживает vmess
    "tor": "S35tor",
}

class ServiceManager:
    """
    Управляет службами (прокси-клиентами) на роутере.
    """

    async def get_all_statuses(self) -> str:
        """
        Проверяет статус всех известных служб и возвращает отформатированную строку.
        """
        status_report = []
        for name, script in SERVICE_NAMES.items():
            command = f"/opt/etc/init.d/{script} status"
            return_code, stdout, stderr = await run_command(command)

            status_icon = "❓" # Неизвестно
            status_text = "не найден"

            if return_code == 0:
                if "running" in stdout.lower():
                    status_icon = "✅"
                    status_text = "Запущен"
                elif "stopped" in stdout.lower() or "not running" in stdout.lower():
                    status_icon = "❌"
                    status_text = "Остановлен"
                else:
                    status_icon = "🤔"
                    status_text = "Неясный статус"
            
            status_report.append(f"{status_icon} {name.capitalize()}: {status_text}")

        if not status_report:
            return "Не найдено ни одной службы для проверки."
            
        return "\n".join(status_report)

    async def restart_service(self, service_name: str) -> tuple[bool, str]:
        """
        Перезапускает указанную службу.
        Возвращает (True, "Успех") или (False, "Текст ошибки").
        """
        script_name = SERVICE_NAMES.get(service_name.lower())
        if not script_name:
            return False, f"Служба '{service_name}' не найдена."

        command = f"/opt/etc/init.d/{script_name} restart"
        return_code, stdout, stderr = await run_command(command)

        if return_code == 0:
            return True, f"Служба '{service_name}' успешно перезапущена."
        else:
            return False, f"Ошибка перезапуска службы '{service_name}':\n{stdout}\n{stderr}"
