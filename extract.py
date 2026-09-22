from pathlib import Path
import logging
import polars as pl


log = logging.getLogger(__name__)
access_format_csv = (".csv",".tsv",".txt")
access_format_excel = (".xlsx",".xlsm")
DEFAULT_REQUIRED_COLUMNS = {'code', 'type_detail', 'date', 'developer', 'machine'}
reqired_columns = set()

READ_OPTIONS_CSV = dict(
    null_values=["", "NULL", "null", "None", "N/A", "-", "nan"],
    encoding="utf8-lossy",
    truncate_ragged_lines=True,
    separator=";",
    has_header=True,
    infer_schema_length = 0
)

EXCEL_READ_OPTIONS = dict(
    read_options={
        "null_values": ["", "NULL", "null", "None", "N/A", "-", "nan"],
        "infer_schema_length": 0,
    },
)


def _check_columns(df: pl.DataFrame, required: set) -> None:
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(
            f"В файле отсутствуют обязательные колонки {sorted(missing)}"
            f"Найдены: {df.columns}"
        )

def check_valid_file(path: Path, acces_format: tuple):
    if not path.exists():
        raise FileNotFoundError(f"Файл по пути {path} отсутствует ")
    if not path.is_file():
        raise IsADirectoryError(f"{path} Ожидался файл , а не директория")
    if path.suffix.lower() not in acces_format:
        raise ValueError(f"Ожидался CSV, получен {path.suffix!r}")



def extract_csv(path: Path,required_columns) -> pl.DataFrame:

    check_valid_file(path,access_format_csv)


    df = pl.read_csv( path, **READ_OPTIONS_CSV)
    _check_columns(df, required_columns or DEFAULT_REQUIRED_COLUMNS)
    log.info("Извлечено %d строк , %d колонок ", df.height,df.width)
    return df


def extract_excel(
    path: Path | str,
    columns: list[str] | None = None,
    required_columns: set | None = None,
) -> pl.DataFrame:

    path = Path(path)
    check_valid_file(path,access_format_excel)

    df = pl.read_excel( path, **EXCEL_READ_OPTIONS )

    if columns:
        # оставляем только запрошенные (после чтения; excel читается целиком)
        keep = [c for c in columns if c in df.columns]
        df = df.select(keep)

    _check_columns(df, required_columns or DEFAULT_REQUIRED_COLUMNS)

    log.debug("Превью:\n%s", df.head(3))

    return df





# ---------------------------------------------------------------------------
# Универсальная точка входа
# ---------------------------------------------------------------------------
def extract(path:str) -> pl.DataFrame:
    path = Path(path)

    ext = path.suffix.lower()
    if ext in access_format_csv:
        return extract_csv(path,reqired_columns)
    if ext in access_format_excel:
        return extract_excel(path,reqired_columns)
    raise ValueError(
        f"расширение {ext} не поддерживается !"
    )


if __name__ == "__main__":
    import sys
    from pprint import pprint

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if len(sys.argv) < 2:
        print("Использование: python extract.py <файл.csv|файл.xlsx>")
        sys.exit(1)

    df = extract(sys.argv[1])
    print("\nСхема:")
    pprint(df.schema)
    print(f"\nРазмер: {df.height} строк × {df.width} колонок")
    print("\nПервые 5 строк:")
    print(df.head(5))
    print("\nСтатистика по null:")
    print(df.null_count())