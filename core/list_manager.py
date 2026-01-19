import os
import glob
from typing import List, Tuple, Optional
from .shell_utils import run_shell_command

# Путь к директории со списками и скрипту обновления
LISTS_DIR = "/opt/etc/kdw/lists"
UPDATE_SCRIPT = "/opt/etc/kdw/scripts/apply_lists.sh"

class ListManager:
    """
    Управляет файлами списков обхода.
    """

    def __init__(self):
        # Создаем директорию для списков при инициализации, если ее нет.
        # Это полезно для локальной разработки.
        os.makedirs(LISTS_DIR, exist_ok=True)

    def get_list_files(self) -> List[str]:
        """
        Возвращает статический список доступных для редактирования списков.
        """
        # В будущем можно сделать этот список динамическим, например, на основе
        # существующих сервисов. Пока что он статический.
        return ["shadowsocks", "trojan", "vmess", "direct"]

    def find_domain(self, domain_to_find: str) -> Optional[str]:
        """
        Ищет домен во всех файлах списков.

        Args:
            domain_to_find: Искомый домен.

        Returns:
            Имя списка, в котором найден домен, или None.
        """
        domain_to_find = domain_to_find.strip()
        for list_name in self.get_list_files():
            file_path = os.path.join(LISTS_DIR, f"{list_name}.list")
            if not os.path.exists(file_path):
                continue
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip() == domain_to_find:
                            return list_name
            except Exception:
                # Игнорируем ошибки чтения, просто ищем дальше
                continue
        return None

    async def move_domain(self, domain: str, from_list: str, to_list: str) -> bool:
        """
        Перемещает домен из одного списка в другой.
        """
        # Шаг 1: Удаляем из старого списка
        await self.remove_from_list(from_list, [domain])
        # Шаг 2: Добавляем в новый список
        await self.add_to_list(to_list, [domain])
        return True

    def read_list(self, list_name: str) -> str:
        """
        Читает содержимое файла списка и возвращает его как строку.
        """
        file_path = os.path.join(LISTS_DIR, f"{list_name}.list")
        if not os.path.exists(file_path):
            # Если файла нет, создадим его
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("")
            return "Список пуст. (Файл был только что создан)"

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content if content.strip() else "Список пуст."
        except Exception as e:
            return f"Ошибка чтения файла: {e}"

    async def add_to_list(self, list_name: str, domains: List[str]) -> bool:
        """
        Добавляет домены в файл списка, избегая дубликатов.
        Возвращает True, если были добавлены новые домены.
        """
        file_path = os.path.join(LISTS_DIR, f"{list_name}.list")
        
        try:
            existing_domains = set()
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    # Читаем только непустые строки
                    existing_domains = set(line.strip() for line in f if line.strip())
            
            initial_count = len(existing_domains)
            
            for domain in domains:
                existing_domains.add(domain.strip())

            if len(existing_domains) > initial_count:
                sorted_domains = sorted(list(existing_domains))
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(sorted_domains) + "\n")
                return True
            return False

        except Exception:
            return False

    async def remove_from_list(self, list_name: str, domains: List[str]) -> bool:
        """
        Удаляет домены из файла списка.
        Возвращает True, если были удалены домены.
        """
        file_path = os.path.join(LISTS_DIR, f"{list_name}.list")
        if not os.path.exists(file_path):
            return False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_domains = set(line.strip() for line in f if line.strip())
            
            initial_count = len(existing_domains)
            domains_to_remove = {d.strip() for d in domains}
            
            # Удаляем домены
            existing_domains -= domains_to_remove

            if len(existing_domains) < initial_count:
                sorted_domains = sorted(list(existing_domains))
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(sorted_domains) + "\n")
                return True
            return False
        except Exception:
            return False

    async def apply_changes(self) -> Tuple[bool, str]:
        """
        Запускает скрипт обновления списков и возвращает результат.
        """
        if not os.path.exists(UPDATE_SCRIPT):
            return False, f"Скрипт обновления `{UPDATE_SCRIPT}` не найден. Запустите установку/обновление бота, чтобы создать его."

        success, output = await run_shell_command(UPDATE_SCRIPT)
        if success:
            return True, "Списки успешно обновлены."
        else:
            return False, f"Ошибка обновления списков:\n`{output}`"
