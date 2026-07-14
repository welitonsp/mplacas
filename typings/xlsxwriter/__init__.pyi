from collections.abc import Mapping, Sequence
from typing import Any, BinaryIO


class Format: ...


class Worksheet:
    def hide_gridlines(self, option: int = ...) -> None: ...
    def freeze_panes(
        self,
        row: int,
        col: int,
        top_row: int | None = ...,
        left_col: int | None = ...,
    ) -> None: ...
    def set_landscape(self) -> None: ...
    def fit_to_pages(self, width: int, height: int) -> None: ...
    def set_margins(
        self,
        left: float = ...,
        right: float = ...,
        top: float = ...,
        bottom: float = ...,
    ) -> None: ...
    def set_header(self, header: str, options: Mapping[str, Any] | None = ...) -> None: ...
    def set_footer(self, footer: str, options: Mapping[str, Any] | None = ...) -> None: ...
    def set_column(
        self,
        first_col: int,
        last_col: int,
        width: float | None = ...,
        cell_format: Format | None = ...,
        options: Mapping[str, Any] | None = ...,
    ) -> int: ...
    def set_row(
        self,
        row: int,
        height: float | None = ...,
        cell_format: Format | None = ...,
        options: Mapping[str, Any] | None = ...,
    ) -> int: ...
    def write(self, row: int, col: int, *args: Any) -> int: ...
    def write_row(
        self,
        row: int,
        col: int,
        data: Sequence[Any],
        cell_format: Format | None = ...,
    ) -> int: ...
    def merge_range(
        self,
        first_row: int,
        first_col: int,
        last_row: int,
        last_col: int,
        data: Any,
        cell_format: Format | None = ...,
    ) -> int: ...
    def add_table(
        self,
        first_row: int,
        first_col: int,
        last_row: int,
        last_col: int,
        options: Mapping[str, Any] | None = ...,
    ) -> int: ...


class Workbook:
    def __init__(
        self,
        filename: str | BinaryIO,
        options: Mapping[str, Any] | None = ...,
    ) -> None: ...
    def add_format(self, properties: Mapping[str, Any] | None = ...) -> Format: ...
    def add_worksheet(self, name: str | None = ...) -> Worksheet: ...
    def set_properties(self, properties: Mapping[str, Any]) -> None: ...
    def close(self) -> None: ...
