# MarketingDailyService — ежедневная рассылка маркетинг-дайджеста в Telegram.
# Разбит на слои:
#   Settings  — чтение/запись настроек (кому слать, в какой час, включено ли)
#   Digest    — формирование данных отчёта (воронка, бюджет, метрики за вчера)
#   Delivery  — отправка через Bot API
#   Helpers   — вспомогательные утилиты (форматирование, шаблоны)
#   Errors    — MarketingDailyDeliveryError, MarketingDailyAccessError

from .marketing_daily_service_delivery import MarketingDailyDeliveryMixin
from .marketing_daily_service_digest import MarketingDailyDigestMixin
from .marketing_daily_service_errors import MarketingDailyAccessError, MarketingDailyDeliveryError
from .marketing_daily_service_helpers import MarketingDailyHelpersMixin
from .marketing_daily_service_settings import MarketingDailySettingsMixin

class MarketingDailyService(
    MarketingDailySettingsMixin,
    MarketingDailyDigestMixin,
    MarketingDailyDeliveryMixin,
    MarketingDailyHelpersMixin,
):
    pass
