from extract import extract
import logging
import polars as pl


log = logging.getLogger(__name__)


STRING_COLUMNS: list[str] = ["type_detail","developer","machine"]

NULL_MARKERS_EXTENDED: list[str] = [
    "", " ", "-", "--",
    "NULL", "null", "Null",
    "None", "NONE",
    "N/A", "n/a", "NA",
    "nan", "NaN", "NAN",
    "нет данных", "нет", "не указано", "неизвестно",
]

DATE_FORMATS: list[str] = [
    "%Y-%m-%d",   # 2026-02-01
    "%d.%m.%Y",   # 01.02.2026
    "%d/%m/%Y",   # 12/07/2024
    "%d %m %Y",   # 01 02 2026
]

def normalize_strings(df:pl.DataFrame,columns: list[str] | None = None) -> pl.DataFrame:

    columns = columns or STRING_COLUMNS
    existing = [c for c in columns if c in df.columns]

    if not existing:
        log.warning(f"в столбцах {columns} нет строковых значений ")
        return df

    return df.with_columns(
        pl.col(existing)
        .str.strip_chars()
        .str.replace_all(r"\s+"," ")
        .str.strip_chars()
        .replace(NULL_MARKERS_EXTENDED, None)
        .str.to_lowercase()
        .str.replace_all("ё","e")

    )

def cast_date(df: pl.DataFrame, col: str = "date") -> pl.DataFrame:
    """
    Пробует несколько форматов даты через coalesce.
    Если ни один не сработал — значение становится null.
    """
    if col not in df.columns:
        log.warning("колонки %r нет в DataFrame, пропускаю cast_date", col)
        return df

    # на случай, если колонка уже Date — не трогаем
    if df[col].dtype == pl.Date:
        return df

    parsed = pl.coalesce([
        pl.col(col).cast(pl.Utf8).str.strptime(pl.Date, fmt, strict=False)
        for fmt in DATE_FORMATS
    ])

    df = df.with_columns(parsed.alias(col))

    # лог: сколько не распозналось
    bad = df[col].is_null().sum()
    if bad:
        log.warning("дата не распознана в %d строках", bad)
    return df




def drop_exact_duplicates(df: pl.DataFrame) -> pl.DataFrame:
    before = df.height
    df = df.unique(maintain_order=True)
    removed = before - df.height
    if removed:
        log.info("Дублей удалено %d", removed)
    return df

def normalize(df:pl.DataFrame) -> pl.DataFrame:
    log.info("DATA_FRAME ДО Нормализации:\n%s", df.head(10))
    log.info("null до:\n%s", df.null_count())

    df = normalize_strings(df)
    df = cast_date(df)
    df = drop_exact_duplicates(df)

    log.info("DATA_FRAME после Нормализации:\n%s", df.head(10))
    log.info("null до:\n%s", df.null_count())

    log.info("данные успешно транформированы")
    return df






