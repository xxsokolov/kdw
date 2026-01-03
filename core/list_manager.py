import os
import glob
from typing import List, Tuple
from .shell_utils import run_shell_command

# Путь к директории со списками и скрипту обновления
LISTS_DIR = "/opt/etc/unblock"
UPDATE_SCRIPT = "/opt/bin/unblock_update.sh"

class ListManager:
    """
    Управляет файлами списков обхода.
    """

    def get_list_files(self) -> List[str]:
        """
        Возвращает список имен файлов .txt из директории списков.
        """
        if not os.path.isdir(LISTS_DIR):
            return []
        
        files = glob.glob(os.path.join(LISTS_DIR, '*.txt'))
        return [os.path.splitext(os.path.basename(f))[0] for f in files]

    def read_list(self, list_name: str) -> str:
        """
        Читает содержимое файла списка и возвращает его как строку.
        """
        file_path = os.path.join(LISTS_DIR, f"{list_name}.txt")
        if not os.path.exists(file_path):
            return "Файл списка не найден."
        
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            return content if content else "Список пуст."
        except Exception as e:
            return f"Ошибка чтения файла: {e}"

    async def add_to_list(self, list_name: str, domains: List[str]) -> bool:
        """
        Добавляет домены в файл списка, избегая дубликатов.
        Возвращает True, если были добавлены новые домены.
        """
        file_path = os.path.join(LISTS_DIR, f"{list_name}.txt")
        
        try:
            existing_domains = set()
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    existing_domains = set(line.strip() for line in f)
            
            initial_count = len(existing_domains)
            
            for domain in domains:
                existing_domains.add(domain.strip())

            if len(existing_domains) > initial_count:
                sorted_domains = sorted(list(existing_domains))
                with open(file_path, 'w') as f:
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
        file_path = os.path.join(LISTS_DIR, f"{list_name}.txt")
        if not os.path.exists(file_path):
            return False

        try:
            with open(file_path, 'r') as f:
                existing_domains = set(line.strip() for line in f)
            
            initial_count = len(existing_domains)
            
            for domain in domains:
                existing_domains.discard(domain.strip())

            if len(existing_domains) < initial_count:
                sorted_domains = sorted(list(existing_domains))
                with open(file_path, 'w') as f:
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
            return False, "Скрипт обновления не найден."

        success, output = await run_shell_command(UPDATE_SCRIPT)
        if success:
            return True, "Списки успешно обновлены."
        else:
            return False, f"Ошибка обновления списков:\n{output}"
