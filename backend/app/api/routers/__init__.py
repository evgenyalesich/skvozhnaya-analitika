# Регистрирует все FastAPI-роутеры в одном месте.
# Каждый модуль = отдельная группа эндпоинтов:
#   admin         — /api/admin/*  (синхронизация, настройки, доступ, репликация)
#   advertising   — /api/advertising-companies/*  (CRUD + rebuild привязки UTM)
#   bots          — /api/bots/*  (реестр ботов)
#   reports       — /api/reports/*  (недельная воронка + вложенные роутеры)
#   reports_extras— /api/reports/subscriptions, touch, budgets/weekly
#   reports_funnel— /api/reports/funnel-start/*  (воронка, raw, экспорт)
#   reports_roistat— /api/reports/roistat-weekly/*  (Roistat + дерево + уроки)
#   utm           — /api/utm/*  (словари UTM для фильтров)

from . import admin, advertising, bots, reports, reports_extras, reports_funnel, reports_roistat, utm

__all__ = ["admin", "advertising", "bots", "reports", "reports_extras", "reports_funnel", "reports_roistat", "utm"]
