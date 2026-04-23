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

type FaqSection = {
  title: string;
  summary: string;
  bullets: string[];
};

const sections: FaqSection[] = [
  {
    title: "Фильтры И Режимы",
    summary: "Как верхняя панель влияет на данные в разных вкладках.",
    bullets: [
      "Верхние фильтры работают для Overview, BOTs, Основного отчёта, Lessons и части Weekly-графиков.",
      "Во вкладке TG SUBS фильтр по периоду учитывается, а фильтры по ботам и РК сверху не применяются.",
      "Во вкладках RAW Users и Поиск верхние фильтры не используются: там отдельная логика фильтрации.",
      "Touch Mode: event / first_touch / last_touch влияет на BOTs и Основной отчёт.",
    ],
  },
  {
    title: "Overview",
    summary: "Главный дашборд по системе и динамике.",
    bullets: [
      "Users at Funnel Start = DISTINCT tg_user_id в текущем срезе.",
      "Total Budget и CAC считаются по таблице бюджетов за выбранный период.",
      "Daily New Users строится по дням, пустые дни показываются с нулём.",
      "Нижние графики по источникам и weekly показывают динамику, а не «финальную» воронку.",
    ],
  },
  {
    title: "BOTs",
    summary: "Воронка по ботам с детализацией по неделям.",
    bullets: [
      "Строки формируются по активным ботам из реестра, даже если за период там нули.",
      "Метрики считаются по unique пользователям (DISTINCT tg_user_id), не по строкам raw.",
      "Бюджет/показы/клики/спенд подтягиваются из рекламных метрик и бюджетов и объединяются с воронкой.",
      "Можно скрывать/показывать столбцы через кнопку «Столбцы»; выбор сохраняется персонально.",
    ],
  },
  {
    title: "Основной Отчёт",
    summary: "Недели → РК/боты, деньги + этапы + конверсии.",
    bullets: [
      "Строится на weekly-данных: отдельно «rows» по РК и «bot_rows» по РК+бот.",
      "entered_all = все старты ботов за неделю, almanah_starts = lead-старты за неделю.",
      "Остальные этапы считаются как факт достижения пользователем этапа в когорте недели.",
      "Колонки в таблице настраиваются и сохраняются для пользователя.",
    ],
  },
  {
    title: "TG SUBS",
    summary: "Сравнение стартов и Telegram-подписок/отписок.",
    bullets: [
      "«Есть в боте» = known users из raw с активным флагом подписки/участия.",
      "«Всего в канале» = общий размер канала по Telegram totals.",
      "Показатель «Не в боте» = участники канала, которых нет в raw_bot_users.",
      "«Мёртвые души» = удалённые аккаунты, которые не удалось достать.",
      "Подписки/отписки за период считаются по событиям и не равны «текущему размеру канала».",
    ],
  },
  {
    title: "PokerHub Lessons",
    summary: "Матрица уроков по пользователям PokerHub.",
    bullets: [
      "Вкладка жёстко работает по lead-когорте (внутри сервиса фильтр bots=[lead]).",
      "Верхний выбор «базы» не переключает источник на другой бот.",
      "Показываются курсы, уроки, даты и прогресс по lesson summary из кэша PokerHub.",
      "Используется для анализа учебного пути, а не для сверки с BOTs 1-в-1.",
    ],
  },
  {
    title: "RAW Users",
    summary: "Сырые строки raw_bot_users без агрегирования по пользователю.",
    bullets: [
      "Одна строка не равна одному пользователю.",
      "Здесь нормально видеть несколько строк на одного tg_user_id.",
      "Именно тут смотрим first_touch/last_touch и проверяем спорные кейсы.",
      "Есть отдельные фильтры по колонкам и отдельное сохранение видимости столбцов.",
      "Используется для диагностики, отладки и поиска причины расхождений.",
      "Экспорт CSV выгружает именно сырые строки.",
    ],
  },
  {
    title: "Поиск",
    summary: "Точечный разбор конкретного пользователя.",
    bullets: [
      "Верхние фильтры не применяются.",
      "Ищет по raw_tg_user_id и username, показывает историю пользователя по записям.",
      "Сразу видно first/last touch, этапы, даты и набор ботов пользователя.",
      "Нужно для разбора кейсов «почему у конкретного человека такая воронка».",
    ],
  },
  {
    title: "Атрибуция И Last Touch",
    summary: "Как работает first_touch / last_touch в текущем продукте.",
    bullets: [
      "First Touch: первый бот пользователя по created_at.",
      "Last Touch: последний бот до первого learn_start_date.",
      "Если learn_start_date нет, last_touch не назначается (в raw обычно «нет метки»).",
      "Поэтому в last_touch режиме часть пользователей нормально не попадает в отчёт.",
    ],
  },
  {
    title: "Счётчик Времени",
    summary: "Что означает время и цвет рядом с «Обновление баз/SM (MSK)».",
    bullets: [
      "В шапке есть live-индикатор статуса обновления и времени последней синхронизации.",
      "Зелёный: данные свежие; показывается текущее время (живой «тикер»), это признак что обновление в норме.",
      "Жёлтый: обновление давно не было или есть проблема по репликации.",
      "Красный: критично давно не обновлялось или была ошибка синка.",
      "Индикатор нужен, чтобы сразу видеть «данным можно доверять сейчас или нет».",
    ],
  },
];

const sourceRules = [
  "BOTs и Основной отчёт сверяем с /api/reports/funnel-start/summary и /api/reports/roistat-weekly/companies-weekly.",
  "Lessons сверяем с PokerHub lesson summary (ph:lesson_summary:*).",
  "RAW Users сверяем с raw_bot_users в том же срезе и сортировке.",
  "TG SUBS сверяем как событийный отчёт Telegram, а не как точную копию raw.",
];

const normalDiffs = [
  "BOTs и Overview могут расходиться по totals: вкладки решают разные задачи и используют разные агрегации.",
  "В Last Touch режиме часть пользователей пропадает из охвата — это нормально без learn_start_date.",
  "TG SUBS не равен размеру канала в Telegram-клиенте 1-в-1 по всем числам.",
  "RAW Users и агрегированные вкладки не должны совпадать построчно.",
  "Показатель «Не в боте» в TG SUBS — это нормально, это участники канала вне raw бот-базы.",
];

const bugSignals = [
  "Пользователь есть в raw, но пропал из вкладки без понятной причины при тех же фильтрах.",
  "Во вкладке появились явно исключённые служебные/тестовые боты.",
  "Одна и та же метрика при одинаковых фильтрах даёт разные значения в одной и той же логике учёта.",
  "В source data есть completion/contract/platform, а в raw поле не обновилось после синка.",
  "У пользователя есть learn_start_date, но last_touch_bot остаётся «нет метки» после пересчёта атрибуции.",
];

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
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            FAQ по вкладкам и логике расчёта
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Памятка для пользователя: что показывает каждая вкладка, как именно считаются цифры и какие расхождения считаются нормой.
          </Typography>
        </Box>

        <Alert severity="info">
          Если цифры отличаются, сначала проверяйте: это баг аналитики или различие источников данных и логики отчёта.
        </Alert>

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Chip label="Актуально под текущий UI" color="primary" variant="outlined" />
          <Chip label="Обновлено под BOTs/Main/TG SUBS" color="default" variant="outlined" />
          <Chip label="Пользовательская версия" color="success" variant="outlined" />
        </Stack>

        <Divider />

        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
            С чем что сверять
          </Typography>
          <Stack spacing={0.75}>
            {sourceRules.map((item) => (
              <Typography key={item} variant="body2">
                • {item}
              </Typography>
            ))}
          </Stack>
        </Box>

        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
            Нормальные расхождения
          </Typography>
          <Stack spacing={0.75}>
            {normalDiffs.map((item) => (
              <Typography key={item} variant="body2">
                • {item}
              </Typography>
            ))}
          </Stack>
        </Box>

        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
            Что считать багом
          </Typography>
          <Stack spacing={0.75}>
            {bugSignals.map((item) => (
              <Typography key={item} variant="body2">
                • {item}
              </Typography>
            ))}
          </Stack>
        </Box>

        <Divider />

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
              <Stack spacing={1}>
                {section.bullets.map((item) => (
                  <Typography key={item} variant="body2">
                    • {item}
                  </Typography>
                ))}
              </Stack>
            </AccordionDetails>
          </Accordion>
        ))}
      </Stack>
    </Paper>
  </Box>
);

export default FaqPanel;
