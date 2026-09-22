"""
Оркестратор ETL-пайплайна.

Порядок:
  1. Extract  — читаем сырой CSV/XLSX в DataFrame (всё Utf8).
  2. Transform — нормализация строк, приведение null-маркеров.
  3. Load     — маппинг на справочники + идемпотентная вставка в PostgreSQL.

Точка входа: `python pipeline.py <файл> [UP|drawings]`
"""

from __future__ import annotations

import logging
import sys

from config import LOGS_DIR
from extract import extract
from load import get_engine, load
from transform import normalize


# ---------------------------------------------------------------------------
# Логирование — настраивается ДО первого log.info
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "etl.log", encoding="utf-8"),
        logging.StreamHandler(),          # вывод в консоль
    ],
    force=True,                            # сбросить любые прежние настройки
)
log = logging.getLogger("pipeline")


# ---------------------------------------------------------------------------
# Оркестратор
# ---------------------------------------------------------------------------

def run(path: str, entity: str = "UP") -> None:
    log.info("=" * 60)
    log.info("=== ETL START ===")
    log.info("Источник : %s", path)
    log.info("Сущность : %s", entity)

    # ----- 1. EXTRACT -----
    log.info("--- EXTRACT ---")
    raw = extract(path)
    log.info("Extract: %d строк, %d колонок", raw.height, raw.width)
    log.info("Колонки: %s", raw.columns)

    # ----- 2. TRANSFORM -----
    log.info("--- TRANSFORM ---")
    clean = normalize(raw)
    log.info("Transform: %d строк после очистки", clean.height)

    # ----- 3. LOAD -----
    log.info("--- LOAD ---")
    engine = get_engine()
    try:
        stats = load(clean, entity=entity, engine=engine)
    finally:
        engine.dispose()

    # ----- ИТОГИ -----
    log.info("=" * 60)
    log.info(
        "=== ETL DONE: вход=%d, вставлено=%d, пропущено=%d, отброшено=%d ===",
        raw.height,
        stats["inserted"],
        stats["skipped"],
        len(stats["errors"]),
    )

    # Дублируем в stdout — удобно для быстрого взгляда
    print(
        f"\nИтог: вход {raw.height}, "
        f"вставлено {stats['inserted']}, "
        f"пропущено {stats['skipped']}, "
        f"отброшено {len(stats['errors'])}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _usage() -> None:
    print(
        "Использование: python pipeline.py <файл.csv|файл.xlsx> [UP|drawings]\n"
        "  пример: python pipeline.py input/up_raw.csv UP"
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        _usage()
        sys.exit(1)

    input_path = sys.argv[1]
    entity = sys.argv[2] if len(sys.argv) > 2 else "UP"

    try:
        run(input_path, entity)
    except FileNotFoundError as e:
        log.error("Файл не найден: %s", e)
        sys.exit(2)
    except ValueError as e:
        log.error("Ошибка данных: %s", e)
        sys.exit(3)
    except Exception:
        log.exception("Непредвиденная ошибка пайплайна")
        sys.exit(1)