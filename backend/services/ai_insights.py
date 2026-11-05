
import json
import os
from datetime import date
from typing import Any

from backend.services.financial_reports import (
    get_dashboard_summary,
    get_profit_loss,
)


def generate_financial_insights(
    db,
    start_date: date | None = None,
    end_date: date | None = None,
) -> str:
    """
    Generate AI commentary using figures calculated by the database.

    Financial figures are sourced from the reporting service.
    Gemini is only used to explain trends, risks, and possible actions.
    """

    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY is missing. Add your Gemini API key to the .env file."
        )

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as exc:
        raise RuntimeError(
            "Gemini integration is not installed. "
            "Install langchain-google-genai."
        ) from exc

    dashboard = get_dashboard_summary(db, start_date, end_date)
    profit_loss = get_profit_loss(db, start_date, end_date)

    financial_data: dict[str, Any] = {
        "period": {
            "start_date": str(start_date) if start_date else None,
            "end_date": str(end_date) if end_date else None,
        },
        "dashboard": dashboard,
        "profit_loss": profit_loss,
    }

    prompt = f"""
You are a careful business financial analyst.

Analyze the financial information provided below.

STRICT RULES:
1. Use only the figures provided in the financial data.
2. Never invent, estimate, or recalculate financial amounts.
3. If a figure is missing, say it is unavailable.
4. Clearly distinguish facts from possible explanations.
5. Do not claim that a trend exists unless the data supports it.
6. Do not present your response as an audited financial statement.
7. Give practical recommendations suitable for a small or medium business.

Return your response using these headings:

## Business Performance
Explain the available revenue, expenses, and profit figures.

## Financial Risks
Identify risks supported by the supplied information.

## Cost Control
Suggest practical ways to review or control expenses.

## Recommended Actions
Give up to five clear actions the business owner can take.

## Important Notes
Mention missing information or limitations in the supplied data.

Financial data:
{json.dumps(financial_data, default=str, indent=2)}
"""

    model = ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        google_api_key=api_key,
        temperature=0.2,
    )

    response = model.invoke(prompt)

    content = response.content

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        return "\n".join(
            str(item.get("text", item))
            if isinstance(item, dict)
            else str(item)
            for item in content
        )

    return str(content)
