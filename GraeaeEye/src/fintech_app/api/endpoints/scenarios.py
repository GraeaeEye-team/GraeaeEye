"""
API-эндпоинты выполнения интерактивных стресс-сценариев What-If.
Принимает гипотезы пользователя (задержка платежей, издержки) и отдает пересчитанный прогноз с SHAP-факторами.
"""
from fastapi import APIRouter

router = APIRouter()


@router.post("/scenarios/simulate", summary="Запустить What-If симуляцию")
async def simulate_scenario():
    """Симулирует пользовательские изменения условий деятельности компании."""
    return {"status": "simulated"}

