// FAQ-панель с аккордеоном: объяснения терминов и бизнес-логики воронки.
import React from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

// Bullet может быть строкой или объектом с вложенными пунктами
type FaqBullet =
  | string
  | { text: string; sub?: string[]; code?: boolean };

type FaqSection = {
  title: string;
  summary: string;
  bullets: FaqBullet[];
};

// ─── данные ──────────────────────────────────────────────────────────────────

const sections: FaqSection[] = [
  // ── ФИЛЬТРЫ ──────────────────────────────────────────────────────────────
  {
    title: "Фильтры и режимы",
    summary: "Как верхняя панель влияет на данные в разных вкладках.",
    bullets: [
      "Период (event_start / event_end) — дата created_at в raw_bot_users (когда пришёл в бот).",
      "Фильтры по ботам и РК работают для Overview, BOTs, Основного отчёта.",
      "Во вкладке TG SUBS фильтр по периоду учитывается, фильтры по ботам/РК — нет.",
      "В RAW Users и Поиске верхние фильтры не применяются — там отдельная логика.",
      {
        text: "Touch Mode меняет логику атрибуции:",
        sub: [
          "event (по умолчанию) — группировка по advertising_company записи бота",
          "first_touch — по боту первого касания пользователя",
          "last_touch — по боту последнего касания ДО регистрации на платформе",
        ],
      },
      "UTM-фильтры используют OR-логику: (utm_source = X) OR (platform_utm_source = X).",
      "Все UTM-значения нормализуются: нижний регистр, trim. None / '(none)' → 'нет метки'.",
    ],
  },

  // ── OVERVIEW ─────────────────────────────────────────────────────────────
  {
    title: "Overview",
    summary: "Главный дашборд: KPI и динамика по системе.",
    bullets: [
      "KPI-карточки = агрегат за выбранный период: Entered, Lead, Platform, Learning, Course, Interview, Offer, Contract.",
      "Entered = COUNT(DISTINCT tg_user_id) по всем записям в raw_bot_users за период.",
      "Total Budget и CAC считаются по таблице бюджетов (budget_weekly) за период.",
      "График Daily New Users строится по agg_daily_new_users — пустые дни показываются с нулём.",
      "Данные берутся из агрегатных таблиц, а не из прямого COUNT по raw_bot_users.",
    ],
  },

  // ── BOTS ─────────────────────────────────────────────────────────────────
  {
    title: "BOTs — воронка по ботам",
    summary: "Разбивка воронки по каждому Telegram-боту.",
    bullets: [
      "Endpoint: GET /api/reports/roistat-weekly/companies-weekly — использует поле bot_rows в ответе.",
      "Каждая строка = один бот, агрегат за весь выбранный период.",
      "Все метрики считаются по уникальным пользователям (DISTINCT tg_user_id), не по строкам raw.",
      {
        text: "Этапы воронки в BOTs:",
        sub: [
          "entered_all — все старты бота за период",
          "almanah_starts — пришли через almanah-боты (органический источник, не direct)",
          "direct_source_cnt — прямые лиды (bot_key LIKE 'lead%' И ph_user_id = tg_user_id)",
          "platform_cnt — зарегистрировались на PokerHub",
          "started_learning — начали обучение",
          "completed_course — прошли курс",
          "interview_reached → offer_received → contract_signed",
        ],
      },
      "При раскрытии строки бота — помесячная разбивка. Данные берутся из того же endpoint с фильтром bots=<bot_key>.",
      "Колонки настраиваются кнопкой «Столбцы»; выбор сохраняется персонально.",
      "Бюджет и рекламные метрики (impressions/clicks/spend) подтягиваются из budget_weekly и ad_metrics_weekly.",
    ],
  },

  // ── ОСНОВНОЙ ОТЧЁТ ───────────────────────────────────────────────────────
  {
    title: "Основной отчёт",
    summary: "Детальный отчёт: недели × РК × боты + деньги + конверсии.",
    bullets: [
      "Endpoint: тот же companies-weekly, но с display_mode=weekly → данные по каждой неделе отдельно.",
      "Строки ответа: rows — по РК, bot_rows — по РК+бот, week_totals — итоги по неделям.",
      "entered_all = все старты ботов за неделю; almanah_starts = лид-старты за неделю.",
      "Остальные этапы = факт достижения пользователем этапа в когорте той недели.",
      {
        text: "Рекламные метрики:",
        sub: [
          "CPF = spend / подписчиков (Cost per Follow — подписчик в канал)",
          "CPL = spend / лидов (Cost per Lead)",
          "CPA = spend / обучения (Cost per Acquisition = старт обучения)",
          "CPC = spend / контрактов (Cost per Contract — НЕ клик!)",
          "CTR = клики / показы × 100% (Click-Through Rate)",
          "CPCₗ = spend / клики (Cost per Click по объявлению)",
          "CPM = spend / показы × 1000 (Cost per Mille)",
        ],
      },
      "Если spend = 0, в формулах используется budget (плановый бюджет).",
      "Если знаменатель = 0 — метрика не показывается (null, а не 0 или ∞).",
      "Данные кэшируются в localStorage (ключ v15, TTL 12h): при открытии сразу виден кэш, фоном грузятся свежие данные.",
    ],
  },

  // ── TG SUBS ──────────────────────────────────────────────────────────────
  {
    title: "TG SUBS",
    summary: "Сравнение стартов ботов и Telegram-подписок/отписок.",
    bullets: [
      "Источник: агрегат agg_tg_subs_daily — события подписки по дням.",
      "«Всего в канале» = общий размер канала из telegram_chat_totals (данные MTProto).",
      "«Есть в боте» = участники канала, которые есть в raw_bot_users.",
      "«Не в боте» = участники канала, которых нет в raw (нормальная ситуация).",
      "«Мёртвые души» = удалённые аккаунты Telegram.",
      "Подписки/отписки за период ≠ текущий размер канала (это потоки, а не остаток).",
      "Два источника данных: bot_poll (события от ботов) и MTProto (полный снимок).",
      "Фильтры по ботам/РК сверху на TG SUBS не влияют — только период.",
    ],
  },

  // ── POKERHUB ─────────────────────────────────────────────────────────────
  {
    title: "PokerHub — уроки и прогресс",
    summary: "Матрица уроков пользователей PokerHub.",
    bullets: [
      "Источник: ph_user_mirror_replica.lessons — JSON-массив пройденных уроков.",
      "Жёстко работает по lead-когорте: внутри сервиса фильтр bots=[lead].",
      "Верхний выбор «базы» не переключает источник на другой бот.",
      "Показывает: курсы (MTT/SPIN/CASH/Базовый), уроки, даты, прогресс.",
      "Используется для анализа учебного пути, не для сверки с BOTs 1-в-1.",
      "ph_user_mirror_replica реплицируется непрерывно через WAL replication из PokerHub.",
    ],
  },

  // ── RAW USERS ────────────────────────────────────────────────────────────
  {
    title: "RAW Users",
    summary: "Сырые строки raw_bot_users без агрегирования.",
    bullets: [
      "1 строка ≠ 1 пользователь. Одному tg_user_id соответствует несколько строк (по числу ботов).",
      "Именно здесь смотрим first_touch_bot, last_touch_bot и проверяем спорные кейсы.",
      "Сотрудники из employee_registry исключены из выдачи.",
      "Отдельные фильтры по колонкам, отдельное сохранение видимости столбцов.",
      "Экспорт CSV/XLSX выгружает именно сырые строки с текущими фильтрами.",
      "Используется для диагностики, отладки и поиска причин расхождений.",
    ],
  },

  // ── ПОИСК ────────────────────────────────────────────────────────────────
  {
    title: "Поиск",
    summary: "Точечный разбор конкретного пользователя.",
    bullets: [
      "Верхние фильтры не применяются.",
      "Поиск по tg_user_id или @username.",
      "Показывает всю историю: все боты, все даты, все этапы воронки, first/last touch.",
      "Нужно для разбора кейсов «почему у конкретного человека такая воронка».",
    ],
  },

  // ── ВОРОНКА ──────────────────────────────────────────────────────────────
  {
    title: "Воронка — определение каждого шага",
    summary: "Точные SQL-условия для каждого из 14 этапов.",
    bullets: [
      "Воронка строго последовательная: каждый следующий шаг включает всех из предыдущего.",
      {
        text: "Этапы (условия из raw_bot_users):",
        sub: [
          "1. Entered — COUNT(DISTINCT tg_user_id) за период",
          "2. New in system — впервые появился в экосистеме (MIN created_at = эта запись)",
          "3. Old in system — уже был раньше (MIN created_at < этой записи)",
          "4. Lead — converted_to_lead IS TRUE или bot_key LIKE 'lead%'",
          "5. Subscribed — channel_subscribed IS TRUE",
          "6. Platform — registered_platform IS TRUE + ph_user_id IS NOT NULL",
          "7. Learning — зарегистрировался на курс (по lessons в ph_user_mirror_replica)",
          "8. Started Learning — started_learning IS TRUE или learn_start_date IS NOT NULL",
          "9. Course — completed_course IS TRUE + completed_course_at >= created_at",
          "10. Interview — interview_reached IS TRUE",
          "11. Passed — interview_passed IS TRUE",
          "12. Offer — offer_received IS TRUE",
          "13. Contract — contract_signed IS TRUE",
          "14. Distance Grinding — distance_grinding IS TRUE",
        ],
      },
      {
        text: "Источники статусов:",
        sub: [
          "converted_to_lead, channel_subscribed, started_learning — из ингестии ботов",
          "registered_platform, platform_registered_at — из PokerHub API",
          "completed_course, interview_reached, offer_received, contract_signed — из Google Sheets (SM)",
          "distance_grinding — парсится из текстов Google Sheets ('наигрывают_дистанцию')",
        ],
      },
      "New + Old = Entered всегда (это разбивка, а не отдельные воронки).",
    ],
  },

  // ── ATTRIBUTION ──────────────────────────────────────────────────────────
  {
    title: "Атрибуция: first_touch и last_touch",
    summary: "Как определяется источник пользователя.",
    bullets: [
      {
        text: "first_touch — самый ранний бот пользователя, исключая lead-боты:",
        sub: [
          "ORDER BY created_at ASC → берём ПЕРВУЮ запись",
          "Исключаем все боты LIKE 'lead%'",
          "UTM-кампания: platform_utm_campaign имеет приоритет над utm_campaign",
        ],
      },
      {
        text: "last_touch — последний бот ДО регистрации на платформе (platform_registered_at):",
        sub: [
          "ORDER BY created_at DESC → берём ПОСЛЕДНЮЮ запись ДО platform_registered_at",
          "Если у пользователя нет platform_registered_at → last_touch = 'нет метки'",
          "Граница именно platform_registered_at, а не learn_start_date",
        ],
      },
      "Почему platform_registered_at, а не learn_start_date: регистрация = точка конверсии. Обучение может начаться через недели, за которые пользователь мог сменить бот.",
      "Пересчёт атрибуции запускается автоматически после ингестии или вручную через admin → Attribution Rebuild.",
      "В режиме last_touch часть пользователей выпадет из отчёта — это нормально (нет platform_registered_at).",
    ],
  },

  // ── ФОРМУЛЫ ──────────────────────────────────────────────────────────────
  {
    title: "Все формулы и метрики",
    summary: "CPF, CPL, CPA, CPC, CTR, CPM и конверсии — точные формулы.",
    bullets: [
      {
        text: "Базовая сумма:",
        sub: [
          "spend_base = spend (если > 0) или budget (если spend = 0)",
        ],
      },
      {
        text: "Рекламные метрики:",
        sub: [
          "CPF = spend_base / subscribed    — стоимость подписчика в канал",
          "CPL = spend_base / lead           — стоимость лида (переход в лид-бот)",
          "CPA = spend_base / learning       — стоимость старта обучения",
          "CPC = spend_base / contract       — стоимость подписанного контракта (НЕ клик!)",
          "CTR = clicks / impressions × 100 — кликабельность в %",
          "CPCₗ = spend_base / clicks        — стоимость клика по объявлению",
          "CPM = spend_base / impressions × 1000 — стоимость 1000 показов",
        ],
      },
      "Все суммы в USD. Конвертации валют нет.",
      "Если знаменатель = 0 → метрика = null (не показывается).",
      {
        text: "Конверсии воронки:",
        sub: [
          "CR(A→B) = count(B) / count(A) × 100%",
          "Например: lead/entered × 100 = конверсия вошли→лид",
        ],
      },
      {
        text: "Course Mix:",
        sub: [
          "MTT%  = mtt  / total_learning × 100",
          "SPIN% = spin / total_learning × 100",
          "CASH% = cash / total_learning × 100",
        ],
      },
    ],
  },

  // ── АГРЕГАТЫ ─────────────────────────────────────────────────────────────
  {
    title: "Агрегаты и пересчёт",
    summary: "Какие таблицы агрегируются, когда и за какой период.",
    bullets: [
      {
        text: "Агрегатные таблицы:",
        sub: [
          "agg_daily_new_users — новые пользователи по дням (группировка: день + bot_key + utm + company)",
          "agg_tg_subs_daily — подписки по дням (день + campaign + bot_key + utm)",
          "agg_weekly_funnel_bot — воронка по неделям × бот",
          "agg_weekly_funnel_company — воронка по неделям × рекламная компания",
        ],
      },
      "Глубина пересчёта: 90 дней назад (aggregate_refresh_days в .env).",
      "Запускается автоматически после репликации (debounce ~60с).",
      "Вручную: admin-панель → Refresh Aggregates (или POST /api/admin/refresh-agg).",
      "Почему только 90 дней: данные старше не меняются. Полный пересчёт занял бы минуты vs секунды.",
      "После деплоя с изменёнными формулами агрегации — нужен ручной запуск пересчёта.",
      "Все даты в агрегатах в московском времени (MSK, UTC+3).",
    ],
  },

  // ── КЭШ ──────────────────────────────────────────────────────────────────
  {
    title: "Кэш и обновления данных",
    summary: "Redis TTL, stale-кэш и localStorage на фронтенде.",
    bullets: [
      {
        text: "TTL по типам данных:",
        sub: [
          "Стандартные отчёты: 5 минут",
          "Недельные агрегаты (companies-weekly): 24 часа",
          "Stale-кэш недельных данных: 7 суток (резерв)",
          "Фильтрованные запросы: не кэшируются",
        ],
      },
      "Stale-кэш: при недоступности БД отдаются данные из stale. Дашборд работает даже во время обслуживания.",
      "Индикатор в шапке: зелёный = данные свежие, жёлтый = давно не обновлялось, красный = критично.",
      "Фронтенд дополнительно кэширует в localStorage (ключ v15, TTL 12h): при открытии сразу виден кэш.",
      "Принудительное обновление: кнопка «Обновить базы» в сайдбаре или прямо в шапке страницы.",
    ],
  },

  // ── СЧЁТЧИК ВРЕМЕНИ ──────────────────────────────────────────────────────
  {
    title: "Счётчик времени в шапке",
    summary: "Что означает цвет и время рядом с «Обновление баз/SM (MSK)».",
    bullets: [
      "Показывает время последней успешной синхронизации данных.",
      "Зелёный + тикер: данные свежие, обновление в норме.",
      "Жёлтый: обновление давно не было или есть проблема по репликации.",
      "Красный: критично давно не обновлялось или была ошибка синка.",
      "Отдельно отслеживается: обновление баз (репликация) и SM (Google Sheets).",
      "Нужен, чтобы сразу видеть «данным можно доверять сейчас или нет».",
    ],
  },

  // ── DISTANCE GRINDING ────────────────────────────────────────────────────
  {
    title: "Distance Grinding — что это",
    summary: "Особый HR-статус между Course и Interview.",
    bullets: [
      "Пользователь прошёл курс, но ему поставлена задача наиграть дистанцию (число рук в покере) перед следующим шагом.",
      "Парсится из текстовых статусов Google Sheets: поля interview_reached_status или offer_received_status.",
      "Значения: 'наигрывают_дистанцию' или 'нагрывают_дистанцию' (нормализуются).",
      "В воронке — отдельный счётчик distance_grinding (не входит в стандартный chain).",
      "Показывается в BOTs и Основном отчёте как отдельная колонка.",
    ],
  },

  // ── АВТОРИЗАЦИЯ ──────────────────────────────────────────────────────────
  {
    title: "Авторизация и доступ",
    summary: "Telegram OTP + JWT. Как добавить пользователя.",
    bullets: [
      "Вход через Telegram: вводишь свой Telegram ID → бот присылает код → вводишь код → доступ открыт.",
      "JWT хранится в HttpOnly cookie (7 дней), не виден JavaScript.",
      {
        text: "Кто имеет доступ:",
        sub: [
          "Фиксированные Telegram ID из .env (initial_allowed_telegram_ids) — всегда",
          "Пользователи из таблицы telegram_access — добавляются через admin-панель",
        ],
      },
      "Добавить пользователя: сайдбар → Доступы → ввести tg_user_id.",
      "Сотрудники (employee_registry) — это отдельно! Они исключаются из аналитики, но могут иметь доступ к дашборду.",
    ],
  },
];

// ─── статичные блоки ──────────────────────────────────────────────────────────

const sourceRules = [
  "BOTs и Основной отчёт сверяем с /api/reports/roistat-weekly/companies-weekly.",
  "PokerHub Lessons сверяем с ph_user_mirror_replica.lessons в той же когорте.",
  "RAW Users сверяем с raw_bot_users в том же срезе и сортировке.",
  "TG SUBS сверяем как событийный отчёт — не точная копия размера канала.",
  "Overview сверяем с agg_weekly_funnel_bot / agg_daily_new_users.",
];

const normalDiffs = [
  "BOTs и Overview могут расходиться: вкладки решают разные задачи и используют разные агрегации.",
  "BOTs ≠ сумма по неделям в Основном отчёте: BOTs считает уника за весь период, Основной — за каждую неделю отдельно.",
  "В режиме last_touch часть пользователей пропадает из охвата — нет platform_registered_at, это нормально.",
  "TG SUBS не равен размеру канала в Telegram-клиенте 1-в-1.",
  "RAW Users и агрегированные вкладки не должны совпадать построчно — разная логика агрегации.",
  "«Не в боте» в TG SUBS — нормально, это участники канала вне бот-базы.",
];

const bugSignals = [
  "Пользователь есть в raw, но пропал из вкладки без понятной причины при тех же фильтрах.",
  "Одна и та же метрика при одинаковых фильтрах даёт разные значения в одной логике учёта.",
  "В raw поле не обновилось после синка, хотя источник (Sheets/PokerHub) уже показывает новое значение.",
  "У пользователя есть platform_registered_at, но last_touch_bot остаётся 'нет метки' после пересчёта атрибуции.",
  "Появились явно исключённые служебные/тестовые боты в отчётах.",
];

const quickActions = [
  "Данные устарели → сайдбар → «Обновить базы» (или admin → Refresh Aggregates).",
  "Нужно пересчитать атрибуцию → admin → Attribution Rebuild.",
  "Добавить нового пользователя → admin → Доступы → tg_user_id.",
  "Добавить сотрудника (исключить из аналитики) → admin → Сотрудники.",
  "Нашёл баг или расхождение → сначала проверь RAW Users с теми же фильтрами.",
  "После деплоя с изменёнными формулами → admin → Refresh Aggregates.",
];

// ─── render ───────────────────────────────────────────────────────────────────

const renderBullet = (item: FaqBullet, idx: number) => {
  if (typeof item === "string") {
    return (
      <Typography key={idx} variant="body2">
        • {item}
      </Typography>
    );
  }
  return (
    <Box key={idx}>
      <Typography variant="body2" sx={{ fontWeight: item.sub ? 600 : 400 }}>
        • {item.text}
      </Typography>
      {item.sub && (
        <Stack spacing={0.5} sx={{ pl: 2.5, pt: 0.25 }}>
          {item.sub.map((s, si) => (
            <Typography
              key={si}
              variant="body2"
              sx={
                item.code
                  ? { fontFamily: "monospace", fontSize: "0.78rem", color: "text.secondary" }
                  : { color: "text.secondary" }
              }
            >
              – {s}
            </Typography>
          ))}
        </Stack>
      )}
    </Box>
  );
};

const FaqPanel: React.FC = () => (
  <Box sx={{ mt: 2 }}>
    <Paper
      sx={{
        p: 3,
        borderRadius: 3,
        background: "linear-gradient(180deg, rgba(248,250,252,0.98) 0%, rgba(255,255,255,1) 22%)",
        boxShadow: "0 18px 40px rgba(15, 23, 42, 0.08)",
      }}
    >
      <Stack spacing={2}>
        {/* заголовок */}
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            FAQ по вкладкам и логике расчёта
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Что показывает каждая вкладка, как именно считаются цифры и какие расхождения считаются нормой.
          </Typography>
        </Box>

        <Alert severity="info">
          Если цифры отличаются, сначала проверяйте: это баг аналитики или различие источников данных и логики отчёта.
        </Alert>

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Chip label="Актуально под текущий UI" color="primary" variant="outlined" />
          <Chip label="Overview · BOTs · Основной отчёт · TG SUBS · PokerHub · RAW · Поиск" color="default" variant="outlined" />
        </Stack>

        <Divider />

        {/* С чем сверять */}
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
            С чем что сверять
          </Typography>
          <Stack spacing={0.75}>
            {sourceRules.map((item) => (
              <Typography key={item} variant="body2">• {item}</Typography>
            ))}
          </Stack>
        </Box>

        {/* Нормальные расхождения */}
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
            Нормальные расхождения
          </Typography>
          <Stack spacing={0.75}>
            {normalDiffs.map((item) => (
              <Typography key={item} variant="body2">• {item}</Typography>
            ))}
          </Stack>
        </Box>

        {/* Что считать багом */}
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
            Что считать багом
          </Typography>
          <Stack spacing={0.75}>
            {bugSignals.map((item) => (
              <Typography key={item} variant="body2">• {item}</Typography>
            ))}
          </Stack>
        </Box>

        {/* Быстрые действия */}
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
            Быстрые действия
          </Typography>
          <Stack spacing={0.75}>
            {quickActions.map((item) => (
              <Typography key={item} variant="body2">• {item}</Typography>
            ))}
          </Stack>
        </Box>

        <Divider />

        {/* Аккордеоны */}
        {sections.map((section) => (
          <Accordion key={section.title} disableGutters sx={{ borderRadius: 2, overflow: "hidden" }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  {section.title}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {section.summary}
                </Typography>
              </Box>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={0.75}>
                {section.bullets.map((item, idx) => renderBullet(item, idx))}
              </Stack>
            </AccordionDetails>
          </Accordion>
        ))}
      </Stack>
    </Paper>
  </Box>
);

export default FaqPanel;
