"""
Excel Read Tool - Read Excel files (.xlsx, .xls) and return sheet data.

Uses pandas with openpyxl (.xlsx) or xlrd (.xls) to read sheets and return
column names and rows as JSON-friendly structures.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd
from fastmcp import FastMCP


def register_tools(mcp: FastMCP) -> None:
    """Register Excel read tools with the MCP server."""

    @mcp.tool()
    def excel_read(
        file_path: str,
        sheet: str | int | None = None,
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        """
        Read an Excel file and return sheet data as columns and rows.

        Use for reading .xlsx or .xls files (e.g. SEC 10-K Excel, financial data).
        Returns one sheet with columns and rows (list of dicts).

        Args:
            file_path: Path to the Excel file (absolute or relative). Supports .xlsx, .xls.
            sheet: Sheet to read: sheet name (str), 0-based index (int), or None for first sheet.
                Use excel_sheet_names first to list sheets in the file.
            max_rows: Maximum rows to return per sheet (None = all). Use to limit context size.

        Returns:
            Dict with path, name, sheet, sheet_name, columns, rows, row_count; or error dict.
        """
        try:
            path = Path(file_path).resolve()

            if not path.exists():
                return {"error": f"Excel file not found: {file_path}"}
            if not path.is_file():
                return {"error": f"Not a file: {file_path}"}

            suffix = path.suffix.lower()
            if suffix not in (".xlsx", ".xls"):
                return {"error": f"Not an Excel file (expected .xlsx or .xls): {file_path}"}
            engine = "openpyxl" if suffix == ".xlsx" else "xlrd"

            if max_rows is not None and max_rows < 1:
                max_rows = None

            sheet_key = sheet if sheet is not None else 0
            with pd.ExcelFile(path, engine=engine) as xl:
                sheet_names = xl.sheet_names
                if isinstance(sheet_key, int):
                    if sheet_key < 0 or sheet_key >= len(sheet_names):
                        return {"error": f"Sheet index out of range: {sheet_key} (file has {len(sheet_names)} sheets)"}
                    actual_sheet_name = sheet_names[sheet_key]
                else:
                    if sheet_key not in sheet_names:
                        return {"error": f"Sheet not found: {sheet_key!r}"}
                    actual_sheet_name = sheet_key
                df = pd.read_excel(xl, sheet_name=sheet_key)

            if df is None:
                return {"error": f"Sheet not found: {sheet}"}

            # Handle multi-index columns: flatten to strings
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [
                    " ".join(str(c).strip() for c in col if str(c).strip())
                    for col in df.columns
                ]
            columns = [str(c) for c in df.columns]

            # Replace NaN with None for JSON
            df = df.where(pd.notnull(df), None)
            if max_rows is not None:
                df = df.head(max_rows)
            rows = df.to_dict(orient="records")

            def _to_json_safe(val: Any) -> Any:
                if val is None or (isinstance(val, float) and not math.isfinite(val)):
                    return None
                if pd.isna(val):
                    return None
                if hasattr(val, "item"):
                    try:
                        v = val.item()
                        if isinstance(v, float) and not math.isfinite(v):
                            return None
                        return v
                    except (ValueError, AttributeError):
                        return str(val)
                if hasattr(val, "isoformat"):
                    return val.isoformat()
                return val

            for r in rows:
                for k, v in r.items():
                    r[k] = _to_json_safe(v)

            return {
                "path": str(path),
                "name": path.name,
                "sheet": sheet_key,
                "sheet_name": actual_sheet_name,
                "columns": columns,
                "column_count": len(columns),
                "rows": rows,
                "row_count": len(rows),
            }
        except Exception as e:
            return {"error": f"Failed to read Excel: {str(e)}"}

    @mcp.tool()
    def excel_sheet_names(file_path: str) -> dict[str, Any]:
        """
        List sheet names in an Excel file.

        Use before excel_read to choose a sheet by name or index.

        Args:
            file_path: Path to the Excel file (absolute or relative).

        Returns:
            Dict with path and sheet_names list; or error dict.
        """
        try:
            path = Path(file_path).resolve()
            if not path.exists():
                return {"error": f"Excel file not found: {file_path}"}
            if not path.is_file():
                return {"error": f"Not a file: {file_path}"}
            suffix = path.suffix.lower()
            if suffix not in (".xlsx", ".xls"):
                return {"error": f"Not an Excel file (expected .xlsx or .xls): {file_path}"}
            engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
            with pd.ExcelFile(path, engine=engine) as xl:
                sheet_names = list(xl.sheet_names)
            return {
                "path": str(path),
                "name": path.name,
                "sheet_names": sheet_names,
                "sheet_count": len(sheet_names),
            }
        except Exception as e:
            return {"error": f"Failed to list sheets: {str(e)}"}
