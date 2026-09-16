"""
API-эндпоинты получения прогнозов Cash Flow и поведенческого скоринга контрагентов.
Возвращает временной ряд остатков, риски кассового разрыва и список проблемных клиентов.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/forecast/{company_id}", summary="Получить прогноз Cash Flow")
async def get_company_forecast(company_id: int):
    """Возвращает динамику денежного потока и риск кассового разрыва на 30/60/90 дней."""
    return {"company_id": company_id, "forecast": []}

