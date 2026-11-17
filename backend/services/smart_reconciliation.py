
from decimal import Decimal, ROUND_HALF_UP

from backend.schemas import (
    SmartReconciliationCreate,
    SmartReconciliationPreview,
)


ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def calculate_smart_reconciliation(
    payload: SmartReconciliationCreate,
) -> SmartReconciliationPreview:
    """
    Calculate adjusted Cash Book and Bank Statement balances.

    Sign conventions:
    - book_increase: increases Cash Book balance.
    - book_decrease: decreases Cash Book balance.
    - timing_increase: increases Bank Statement balance for comparison.
    - timing_decrease: decreases Bank Statement balance for comparison.

    This function only calculates figures. It does not post journal entries.
    """

    original_cash_book = _money(payload.cash_book_balance)
    original_bank_statement = _money(payload.bank_statement_balance)

    adjusted_cash_book = original_cash_book
    adjusted_bank_statement = original_bank_statement

    book_adjustments_total = ZERO
    timing_adjustments_total = ZERO

    for adjustment in payload.adjustments:
        amount = _money(adjustment.amount)

        if amount <= ZERO:
            raise ValueError(
                "Adjustment amount must be greater than zero."
            )

        if adjustment.effect == "book_increase":
            adjusted_cash_book += amount
            book_adjustments_total += amount

        elif adjustment.effect == "book_decrease":
            adjusted_cash_book -= amount
            book_adjustments_total -= amount

        elif adjustment.effect == "timing_increase":
            adjusted_bank_statement += amount
            timing_adjustments_total += amount

        elif adjustment.effect == "timing_decrease":
            adjusted_bank_statement -= amount
            timing_adjustments_total -= amount

        else:
            raise ValueError(
                f"Unsupported adjustment effect: {adjustment.effect}"
            )

    adjusted_cash_book = _money(adjusted_cash_book)
    adjusted_bank_statement = _money(adjusted_bank_statement)

    difference = _money(
        adjusted_bank_statement - adjusted_cash_book
    )

    result_status = (
        "matched" if difference == ZERO else "unmatched"
    )

    return SmartReconciliationPreview(
        account_id=payload.account_id,
        statement_date=payload.statement_date,
        original_cash_book_balance=original_cash_book,
        adjusted_cash_book_balance=adjusted_cash_book,
        original_bank_statement_balance=original_bank_statement,
        adjusted_bank_statement_balance=adjusted_bank_statement,
        difference=difference,
        status=result_status,
        book_adjustments_total=_money(book_adjustments_total),
        timing_adjustments_total=_money(timing_adjustments_total),
        adjustments=payload.adjustments,
    )
