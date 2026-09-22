"""
Модуль Load для ETL-пайплайна.

Целевая БД — PostgreSQL со схемой public (см. pg_dump).

Особенности:
  - Имена таблиц "Machines", "PC", "UP" — с заглавной буквы, в SQL — в кавычках.
  - "Machines".name — целое (FK на machine_dict.id), а не текст.
  - Натуральных UNIQUE-ключей нет, поэтому идемпотентность через SELECT→INSERT.
  - Справочники (type_detail_dict, machine_dict) только читаем — неизвестные
    значения отклоняем (это требование лабы: «приведение к справочникам»).
  - developers создаём автоматически, если такого нет.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import polars as pl
from sqlalchemy import create_engine, text, Engine
from sqlalchemy.exc import SQLAlchemyError

from config import DB_URL, LOGS_DIR

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Подключение
# ---------------------------------------------------------------------------

def get_engine(db_url: str = DB_URL) -> Engine:
    engine = create_engine(db_url, echo=False, pool_pre_ping=True)
    log.info("Подключение к БД установлено: %s", db_url.split("@")[-1])
    return engine


# ---------------------------------------------------------------------------
# Чтение справочников
# ---------------------------------------------------------------------------

def _read_lookup(engine: Engine, table: str, id_col: str, name_col: str) -> dict[str, int]:
    """
    Возвращает {нижний_регистр_имени: id} из справочной таблицы.
    Для таблиц с заглавными буквами ("Machines", "PC") имя надо квотировать.
    """
    sql = text(f'SELECT "{id_col}", "{name_col}" FROM public."{table}"')
    with engine.connect() as conn:
        rows = conn.execute(sql).all()

    lookup: dict[str, int] = {}
    for r in rows:
        if r[1] is None:
            continue
        lookup[str(r[1]).strip().lower()] = int(r[0])
    return lookup


def build_lookups(engine: Engine) -> dict[str, dict[str, int]]:
    """
    Собираем все справочники, нужные для маппинга.
    """
    lookups = {
        "type_detail":   _read_lookup(engine, "type_detail_dict", "id", "name"),
        "machine_model": _read_lookup(engine, "machine_dict",     "id", "name"),
        "developer":     _read_lookup(engine, "developers",       "id", "name"),
        "pc":            _read_lookup(engine, "PC",               "id", "name"),
    }
    for name, lk in lookups.items():
        log.info("Справочник %-15s: %d записей", name, len(lk))
    return lookups


# ---------------------------------------------------------------------------
# Вспомогательные: поиск / создание
# ---------------------------------------------------------------------------

def _find_machine_id(engine: Engine, machine_model_id: int) -> int | None:
    """Ищем id конкретного станка по id его модели (Machines.name = machine_dict.id)."""
    sql = text('SELECT id FROM public."Machines" WHERE name = :m LIMIT 1')
    with engine.connect() as conn:
        row = conn.execute(sql, {"m": machine_model_id}).first()
    return int(row[0]) if row else None


def _get_or_create_developer(engine: Engine, name: str) -> int:
    """Находит разработчика по имени или создаёт нового."""
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM public.developers WHERE name = :n LIMIT 1"),
            {"n": name},
        ).first()
        if row:
            return int(row[0])

        row = conn.execute(
            text("INSERT INTO public.developers (name) VALUES (:n) RETURNING id"),
            {"n": name},
        ).first()
    return int(row[0])


def _up_exists(engine: Engine, code: str, d: date | None) -> bool:
    """Есть ли уже УП с таким кодом (и датой, если дата задана)."""
    if d is None:
        sql = text('SELECT 1 FROM public."UP" WHERE code = :c LIMIT 1')
        params = {"c": code}
    else:
        sql = text('SELECT 1 FROM public."UP" WHERE code = :c AND date = :d LIMIT 1')
        params = {"c": code, "d": d}
    with engine.connect() as conn:
        return conn.execute(sql, params).first() is not None


# ---------------------------------------------------------------------------
# Загрузка UP
# ---------------------------------------------------------------------------

def load_up(engine: Engine, df: pl.DataFrame, lookups: dict) -> dict:
    """
    Загружает управляющие программы (UP).

    Ожидаемые колонки во входном DataFrame:
        code          str   код УП, обяз.
        type_detail   str   тип детали, обяз., должен быть в type_detail_dict
        date          Date  дата, обяз.
        developer     str   ФИО разработчика, обяз., создаётся при необходимости
        machine       str   модель станка (значение из machine_dict.name), опц.
    """
    type_lookup = lookups["type_detail"]
    machine_lookup = lookups["machine_model"]

    inserted = 0
    skipped = 0
    errors: list[dict] = []

    for row in df.iter_rows(named=True):
        code = row.get("code")
        td_text = row.get("type_detail")
        date_val = row.get("date")
        dev_name = row.get("developer")
        mach_text = row.get("machine")

        # ---- валидация ----
        if not code or not td_text or not dev_name or date_val is None:
            errors.append({**row, "_error": "пустые обязательные поля"})
            continue

        td_id = type_lookup.get(str(td_text).strip().lower())
        if td_id is None:
            errors.append({**row, "_error": f"тип детали не найден в справочнике: {td_text!r}"})
            continue

        # machine: ищем модель станка в справочнике, затем конкретный станок
        machine_id = None
        if mach_text:
            mm_id = machine_lookup.get(str(mach_text).strip().lower())
            if mm_id is None:
                errors.append({**row, "_error": f"модель станка не найдена: {mach_text!r}"})
                continue
            machine_id = _find_machine_id(engine, mm_id)
            if machine_id is None:
                errors.append({**row,
                               "_error": f"нет ни одного станка модели {mach_text!r}"})
                continue

        # ---- идемпотентность ----
        if _up_exists(engine, str(code), date_val):
            skipped += 1
            continue

        # ---- вставка ----
        try:
            developer_id = _get_or_create_developer(engine, str(dev_name).strip())

            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO public."UP"
                            (code, type_detail, date, developer, machine)
                        VALUES
                            (:code, :td, :d, :dev, :m)
                    """),
                    {
                        "code": code,
                        "td":   td_id,
                        "d":    date_val,
                        "dev":  developer_id,
                        "m":    machine_id,
                    },
                )
            inserted += 1
        except SQLAlchemyError as e:
            errors.append({**row, "_error": f"ошибка вставки: {e}"})

    log.info("UP: вставлено %d, пропущено (уже были) %d, ошибок %d",
             inserted, skipped, len(errors))
    return {"inserted": inserted, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Заготовка под drawings (по аналогии — если в твоём варианте грузится это)
# ---------------------------------------------------------------------------

def load_drawings(engine: Engine, df: pl.DataFrame, lookups: dict) -> dict:
    """
    Аналог load_up, но для чертежей.
    Ожидаемые колонки: code, type_detail, developer, version
    """
    type_lookup = lookups["type_detail"]

    inserted = skipped = 0
    errors: list[dict] = []

    for row in df.iter_rows(named=True):
        code = row.get("code")
        td_text = row.get("type_detail")
        dev_name = row.get("developer")
        version = row.get("version")

        if not code or not td_text or not dev_name:
            errors.append({**row, "_error": "пустые обязательные поля"})
            continue

        td_id = type_lookup.get(str(td_text).strip().lower())
        if td_id is None:
            errors.append({**row, "_error": f"тип детали не найден: {td_text!r}"})
            continue

        # дубль по (code, version)
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM public.drawings WHERE code = :c AND version = :v LIMIT 1"),
                {"c": code, "v": version},
            ).first()
        if exists:
            skipped += 1
            continue

        try:
            developer_id = _get_or_create_developer(engine, str(dev_name).strip())
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO public.drawings
                            (code, type_detail, developer, version)
                        VALUES
                            (:code, :td, :dev, :v)
                    """),
                    {"code": code, "td": td_id, "dev": developer_id, "v": version},
                )
            inserted += 1
        except SQLAlchemyError as e:
            errors.append({**row, "_error": f"ошибка вставки: {e}"})

    log.info("drawings: вставлено %d, пропущено %d, ошибок %d",
             inserted, skipped, len(errors))
    return {"inserted": inserted, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Rejects → CSV
# ---------------------------------------------------------------------------

def save_rejects(errors: list[dict], csv_path: Path | None = None) -> Path | None:
    if not errors:
        log.info("Отклонённых строк нет")
        return None
    csv_path = csv_path or (LOGS_DIR / "rejected_rows.csv")
    pl.DataFrame(errors).write_csv(csv_path)
    log.info("Rejects → %s (%d строк)", csv_path, len(errors))
    return csv_path


# ---------------------------------------------------------------------------
# Оркестратор
# ---------------------------------------------------------------------------

def load(df: pl.DataFrame,
         entity: str = "UP",
         engine: Engine | None = None) -> dict:
    """
    Точка входа. Принимает очищенный DataFrame из transform.py.

    entity: "UP" | "drawings"  (какая сущность грузится)
    """
    engine = engine or get_engine()
    lookups = build_lookups(engine)

    if entity == "UP":
        stats = load_up(engine, df, lookups)
    elif entity == "drawings":
        stats = load_drawings(engine, df, lookups)
    else:
        raise ValueError(f"Неизвестная сущность: {entity!r}")

    save_rejects(stats["errors"])
    log.info("Load завершён: %s", {k: v for k, v in stats.items() if k != "errors"})
    return stats