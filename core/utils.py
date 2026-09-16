"""Small shared helpers (app-agnostic)."""
import re


def normalize_reg_no(value: str | None) -> str:
    """Registration numbers: uppercase, trimmed, all internal whitespace removed."""
    return re.sub(r"\s+", "", (value or "")).strip().upper()


def human_size(num_bytes: int) -> str:
    """Bytes -> '1.3 KB', rounded half-up."""
    from decimal import Decimal, ROUND_HALF_UP

    size = Decimal(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)} {unit}"
        size /= 1024
    return f"{size.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)} GB"
