from __future__ import annotations

from decimal import Decimal

from flux.metering.domain import ModelPrice, PriceBook, ReportLine, UsageReport


def _book(prices: dict[str, ModelPrice]) -> PriceBook:
    return PriceBook(
        prices=prices,
        default_prompt_per_1k=Decimal("0.0005"),
        default_completion_per_1k=Decimal("0.0015"),
    )


def test_cost_uses_model_price_when_present() -> None:
    book = _book(
        {
            "gpt-stub": ModelPrice(
                model_name="gpt-stub",
                prompt_per_1k=Decimal("0.001"),
                completion_per_1k=Decimal("0.002"),
            )
        }
    )
    # 2000 prompt tokens at 0.001/1k = 0.002; 1000 completion at 0.002/1k = 0.002
    assert book.cost("gpt-stub", 2000, 1000) == Decimal("0.004000")


def test_cost_falls_back_to_defaults_for_unknown_model() -> None:
    book = _book({})
    # 1000 prompt at 0.0005 = 0.0005; 1000 completion at 0.0015 = 0.0015
    assert book.cost("mystery", 1000, 1000) == Decimal("0.002000")


def test_cost_is_quantized_to_six_places() -> None:
    book = _book({})
    cost = book.cost("mystery", 1, 0)  # 1/1000 * 0.0005 = 0.0000005 -> rounds to 6dp
    assert cost == Decimal("0.000001")  # half-up rounding


def test_report_totals_sum_lines() -> None:
    report = UsageReport(
        tenant="t-1",
        currency="USD",
        lines=[
            ReportLine("a", 100, 50, 2, Decimal("0.001")),
            ReportLine("b", 200, 100, 3, Decimal("0.002")),
        ],
    )
    assert report.total_prompt_tokens == 300
    assert report.total_completion_tokens == 150
    assert report.total_request_count == 5
    assert report.total_cost == Decimal("0.003000")
