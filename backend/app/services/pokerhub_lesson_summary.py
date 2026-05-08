import re
import json
from datetime import datetime
from typing import Any


class PokerHubLessonSummaryBuilder:
    COURSE_ORDER = ("BASE", "MTT_NEW", "SPIN_NEW", "MTT", "SPIN", "CASH")
    TERMINAL_LESSONS = {
        "BASE": (None, 5),
        "MTT_NEW": (None, 12),
        "SPIN_NEW": (None, 80),
        "MTT": (2, 21),
        "SPIN": (1, 81),
        "CASH": (1, 10),
    }

    def build(self, payload: dict[str, Any], course_catalog: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "tg_user_id": self._coerce_int(payload.get("tg_id")),
            "username": self._extract_username(payload),
            "pokerhub_user_id": self._extract_pokerhub_user_id(payload),
            "course_memberships": self._extract_course_memberships(payload, course_catalog or {}),
            "raw_course_labels": self._extract_raw_course_labels(payload),
            "groups": sorted(self._extract_groups(payload)),
            "courses": self._extract_courses(payload, course_catalog or {}),
        }

    def _extract_course_memberships(
        self,
        payload: dict[str, Any],
        course_catalog: dict[str, Any],
    ) -> list[str]:
        memberships: set[str] = set()
        raw_courses = self._parse_json_value(payload.get("courses"))
        groups = self._extract_groups(payload)
        if isinstance(raw_courses, dict):
            for course_key, lessons in raw_courses.items():
                normalized = self._resolve_course(course_key, str(course_key or ""), course_catalog, groups)
                if normalized:
                    memberships.add(normalized)
                lessons = self._parse_json_value(lessons)
                if isinstance(lessons, list):
                    for lesson in lessons:
                        if isinstance(lesson, (list, tuple)) and lesson:
                            detected = self._resolve_course(course_key, str(lesson[0] or ""), course_catalog, groups)
                            if detected:
                                memberships.add(detected)
        elif isinstance(raw_courses, list):
            for item in raw_courses:
                normalized = self._normalize_course(item if isinstance(item, str) else str(item or ""))
                if normalized:
                    memberships.add(normalized)
        return [course for course in self.COURSE_ORDER if course in memberships]

    def _extract_courses(self, payload: dict[str, Any], course_catalog: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, dict[str, dict[str, Any]]] = {course: {} for course in self.COURSE_ORDER}
        courses = self._parse_json_value(payload.get("courses"))
        groups = self._extract_groups(payload)

        if not isinstance(courses, dict) or not courses:
            self._merge_flat_lessons(result, payload.get("lessons"), course_catalog, groups)
            return {
                course: sorted(values.values(), key=self._sort_key)
                for course, values in result.items()
            }

        for course_key, lessons in courses.items():
            lessons = self._parse_json_value(lessons)
            if not isinstance(lessons, list):
                continue
            for lesson in lessons:
                parsed = self._parse_lesson(course_key, lesson, course_catalog, groups)
                if not parsed:
                    continue
                course, entry = parsed
                existing = result[course].get(entry["key"])
                if existing is None:
                    result[course][entry["key"]] = entry
                elif existing.get("date") is None and entry.get("date") is not None:
                    result[course][entry["key"]] = entry
                elif entry.get("date") and existing.get("date") and entry["date"] < existing["date"]:
                    result[course][entry["key"]] = entry

        return {
            course: sorted(values.values(), key=self._sort_key)
            for course, values in result.items()
        }

    def _merge_flat_lessons(
        self,
        result: dict[str, dict[str, dict[str, Any]]],
        raw_lessons: Any,
        course_catalog: dict[str, Any],
        groups: set[str],
    ) -> None:
        lessons = self._parse_json_value(raw_lessons)
        if not isinstance(lessons, list):
            return
        for lesson in lessons:
            parsed = self._parse_flat_lesson(lesson, course_catalog, groups)
            if not parsed:
                continue
            course, entry = parsed
            existing = result[course].get(entry["key"])
            if existing is None:
                result[course][entry["key"]] = entry
            elif existing.get("date") is None and entry.get("date") is not None:
                result[course][entry["key"]] = entry
            elif entry.get("date") and existing.get("date") and entry["date"] < existing["date"]:
                result[course][entry["key"]] = entry

    def _parse_lesson(
        self,
        course_key: Any,
        lesson: Any,
        course_catalog: dict[str, Any],
        groups: set[str],
    ) -> tuple[str, dict[str, Any]] | None:
        if not (isinstance(lesson, (list, tuple)) and len(lesson) >= 2):
            return None
        title = str(lesson[0] or "").strip()
        raw_date = lesson[1]
        course = self._resolve_course(course_key, title, course_catalog, groups)
        if not course:
            return None
        module, lesson_number = self._parse_module_and_lesson(title)
        if not self._is_supported_lesson(course, module, lesson_number):
            return None
        if course == "BASE":
            module = None
        return course, {
            "key": self._build_column_key(module, lesson_number, title),
            "label": self._build_column_label(module, lesson_number, title),
            "module": module,
            "lesson": lesson_number,
            "date": self._parse_date(raw_date),
        }

    def _parse_flat_lesson(
        self,
        lesson: Any,
        course_catalog: dict[str, Any],
        groups: set[str],
    ) -> tuple[str, dict[str, Any]] | None:
        if not isinstance(lesson, str):
            return None
        text = lesson.strip()
        if not text:
            return None
        title, raw_date = self._split_flat_lesson(text)
        course = self._resolve_course(title, title, course_catalog, groups)
        if not course:
            return None
        module, lesson_number = self._parse_module_and_lesson(title)
        if not self._is_supported_lesson(course, module, lesson_number):
            return None
        if course == "BASE":
            module = None
        return course, {
            "key": self._build_column_key(module, lesson_number, title),
            "label": self._build_column_label(module, lesson_number, title),
            "module": module,
            "lesson": lesson_number,
            "date": self._parse_date(raw_date),
        }

    def _split_flat_lesson(self, lesson: str) -> tuple[str, str | None]:
        match = re.match(r"^(.*)\(([^()]+)\)\s*$", lesson)
        if not match:
            return lesson, None
        return match.group(1).strip(), match.group(2).strip()

    def _resolve_course(
        self,
        course_key: Any,
        title: str,
        course_catalog: dict[str, Any],
        groups: set[str],
    ) -> str | None:
        title_norm = self._normalize_title(title)
        combined_upper = f"{course_key} {title}".upper()
        if title_norm:
            spin_new_titles = self._catalog_title_set(course_catalog, "85")
            mtt_new_titles = self._catalog_title_set(course_catalog, "86")
            base_titles = self._catalog_title_set(course_catalog, "83")
            is_spin_after_base = "spin after base couse" in groups
            is_mtt_after_base = "mtt after base couse" in groups
            if title_norm in base_titles:
                return "BASE"
            if is_spin_after_base and (
                title.upper().startswith("SE -SPIN")
            ):
                return "SPIN_NEW"
            if is_mtt_after_base and title_norm in mtt_new_titles:
                return "MTT_NEW"
            # Mirror payloads often contain only generic SPIN1/MTT1 lesson titles
            # plus a group marker that the user is on the post-base SE track.
            if is_spin_after_base and ("SPIN1" in combined_upper or "SPIN " in combined_upper):
                return "SPIN_NEW"
            if is_mtt_after_base and ("MTT1" in combined_upper or "MTT2" in combined_upper or "MTT " in combined_upper):
                return "MTT_NEW"
        return self._normalize_course(f"{course_key} {title}")

    def _normalize_course(self, value: Any) -> str | None:
        if not value or not isinstance(value, str):
            return None
        upper = value.upper()
        compact = " ".join(upper.split())
        if "БАЗОВ" in upper or "BASE COURSE" in upper or upper.strip() == "BASE":
            return "BASE"
        if compact.startswith("86 ") or compact == "86":
            return "MTT_NEW"
        if compact.startswith("85 ") or compact == "85":
            return "SPIN_NEW"
        if "КУРС ДЛЯ НАЧИНАЮЩИХ ИГРОКОВ В ТУРНИРНЫЙ ПОКЕР SE" in upper or "ТУРНИРНЫЙ ПОКЕР SE" in upper:
            return "MTT_NEW"
        if "КУРС ДЛЯ НОВИЧКОВ В SPIN'N'GO SE" in upper or "КУРС ДЛЯ НОВИЧКОВ В SPIN’N’GO SE" in upper or "SPIN'N'GO SE" in upper or "SPIN’N’GO SE" in upper:
            return "SPIN_NEW"
        if "MTT" in upper or "МТТ" in upper:
            return "MTT"
        if "SPIN" in upper or "СПИН" in upper:
            return "SPIN"
        if "CASH" in upper or "КЭШ" in upper or "КЕШ" in upper:
            return "CASH"
        return None

    def _extract_raw_course_labels(self, payload: dict[str, Any]) -> list[str]:
        raw_courses = self._parse_json_value(payload.get("courses"))
        labels: list[str] = []
        if isinstance(raw_courses, dict):
            labels.extend([str(key).strip() for key in raw_courses.keys() if str(key).strip()])
        elif isinstance(raw_courses, list):
            labels.extend([str(item).strip() for item in raw_courses if str(item).strip()])
        return labels

    def _parse_module_and_lesson(self, title: str) -> tuple[int | None, int | None]:
        upper = title.upper()
        module_match = re.search(r"МОДУЛ[ЬЯ]\s*(\d+)", upper)
        lesson_match = re.search(r"УРОК\s*(\d+)", upper)
        module = int(module_match.group(1)) if module_match else None
        lesson = int(lesson_match.group(1)) if lesson_match else None
        return module, lesson

    def _is_supported_lesson(self, course: str, module: int | None, lesson: int | None) -> bool:
        if lesson is None:
            return False
        terminal = self.TERMINAL_LESSONS.get(course)
        if terminal is None:
            return True
        terminal_module, terminal_lesson = terminal
        if course == "BASE":
            return 1 <= lesson <= terminal_lesson
        if course in {"MTT_NEW", "SPIN_NEW"}:
            return 1 <= lesson <= terminal_lesson
        if module is None:
            return False
        if module > terminal_module:
            return False
        if module == terminal_module and lesson > terminal_lesson:
            return False
        return True

    def _build_column_label(self, module: int | None, lesson: int | None, title: str) -> str:
        if module is not None and lesson is not None:
            return f"Модуль {module} / Урок {lesson}"
        if lesson is not None:
            return f"Урок {lesson}"
        return title or "Урок"

    def _build_column_key(self, module: int | None, lesson: int | None, title: str) -> str:
        if module is not None and lesson is not None:
            return f"m{module}_l{lesson}"
        if lesson is not None:
            return f"l{lesson}"
        normalized = re.sub(r"[^a-zA-Z0-9]+", "_", title.strip().lower()).strip("_")
        return normalized or "lesson"

    def _parse_date(self, value: Any) -> str | None:
        if not value or not isinstance(value, str):
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized.replace("T", " "))
        except ValueError:
            return None
        return parsed.date().isoformat()

    def _extract_username(self, payload: dict[str, Any]) -> str | None:
        for key in ("ph_username", "ph_nickname", "tg_username", "username"):
            value = payload.get(key)
            if value:
                return str(value)
        return None

    def _extract_pokerhub_user_id(self, payload: dict[str, Any]) -> str | None:
        for key in ("user_id", "ph_user_id", "ph_id", "id"):
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value)
        return None

    def _extract_groups(self, payload: dict[str, Any]) -> set[str]:
        raw_groups = self._parse_json_value(payload.get("groups"))
        group_values: list[Any] = []
        if isinstance(raw_groups, list):
            group_values.extend(raw_groups)
        raw_group = self._parse_json_value(payload.get("group"))
        if isinstance(raw_group, list):
            group_values.extend(raw_group)
        elif raw_group is not None:
            group_values.append(raw_group)
        return {
            str(group).strip().lower()
            for group in group_values
            if str(group).strip()
        }

    def _coerce_int(self, value: Any) -> int | None:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None

    def _parse_json_value(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            return value
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value

    def _sort_key(self, column: dict[str, Any]) -> tuple[int, int, str]:
        module = column.get("module") if column.get("module") is not None else 999
        lesson = column.get("lesson") if column.get("lesson") is not None else 999
        return module, lesson, str(column.get("label") or "")

    def _catalog_title_set(self, course_catalog: dict[str, Any], course_id: str) -> set[str]:
        course = course_catalog.get(str(course_id))
        if not isinstance(course, dict):
            return set()
        quizzes = course.get("quizzes")
        if not isinstance(quizzes, list):
            return set()
        result = set()
        for quiz in quizzes:
            if not isinstance(quiz, dict):
                continue
            title = self._normalize_title(quiz.get("name"))
            if title:
                result.add(title)
        return result

    def _normalize_title(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text)
        return text.lower()
