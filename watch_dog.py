"""
watcher.py — сервис автоматической загрузки транспортных файлов.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

from config import WATCH_DIR, FILE_EXTENSIONS
from pipeline import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("watcher")


def wait_until_stable(path: Path, timeout: int = 30, interval: float = 1.0) -> bool:
    last_size = -1
    elapsed = 0.0
    while elapsed < timeout:
        if not path.exists():
            return False
        current_size = path.stat().st_size
        if current_size == last_size and current_size > 0:
            return True
        last_size = current_size
        time.sleep(interval)
        elapsed += interval
    return False


class NewFileHandler(PatternMatchingEventHandler):
    def __init__(self):
        super().__init__(
            patterns=[f"*{ext}" for ext in FILE_EXTENSIONS],
            ignore_patterns=["*~", "*.tmp", "*.swp", "*.lock"],
            ignore_directories=True,
            case_sensitive=False,
        )
        # Файлы, которые прямо сейчас обрабатываются — чтобы не запускать
        # параллельно один и тот же файл, если событий прилетит много.
        self._in_progress: set[str] = set()

    # ---------- общая логика для on_created и on_modified ----------

    def _process(self, path: Path, source: str) -> None:
        """Общая точка: дождаться стабилизации и запустить ETL."""
        key = str(path.resolve())

        # Уже обрабатываем этот же файл — пропускаем дубликат события
        if key in self._in_progress:
            log.debug("[%s] %s уже в обработке, пропуск", source, path.name)
            return

        log.info("[%s] Обнаружен файл: %s", source, path.name)

        self._in_progress.add(key)
        try:
            if not wait_until_stable(path):
                log.warning("[%s] Файл %s не стабилизировался, пропуск",
                            source, path.name)
                return

            try:
                run(str(path), entity="UP")
                log.info("[%s] Файл %s успешно обработан", source, path.name)
            except Exception:
                log.exception("[%s] Ошибка обработки файла %s", source, path.name)
        finally:
            self._in_progress.discard(key)

    # ---------- обработчики событий ----------

    def on_created(self, event):
        self._process(Path(event.src_path), source="created")

    def on_modified(self, event):
        self._process(Path(event.src_path), source="modified")

def main() -> None:
    watch_dir = Path(WATCH_DIR)
    if not watch_dir.exists():
        watch_dir.mkdir(parents=True)
        log.info("Создана папка наблюдения: %s", watch_dir)

    handler = NewFileHandler()
    observer = Observer()
    observer.schedule(handler, path=str(watch_dir), recursive=False)
    observer.start()
    log.info("Сервис запущен, следим за %s", watch_dir)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Остановка сервиса...")
        observer.stop()
    observer.join()
    log.info("Сервис остановлен")


if __name__ == "__main__":
    main()