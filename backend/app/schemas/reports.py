from typing import Dict, List, Optional

from pydantic import BaseModel


class WeeklyStageRow(BaseModel):
    week_start: str
    week_end: str
    values: Dict[str, int]


class WeeklyReportResponse(BaseModel):
    group_key: str
    months: Dict[str, List[WeeklyStageRow]]


class RoistatWeeklyRow(BaseModel):
    week_start: str
    almanah_starts: int
    direct_source_cnt: int = 0
    new_in_system: int = 0
    old_in_system: int = 0
    platform: int
    learning: int
    started_learning: int
    mtt: int
    spin: int
    cash: int
    base: int = 0
    not_started: int
    channel_subscribed: int
    saloon: int
    completed_course: int
    completed_base: int = 0
    distance_grinding: int
    contract_signed: int
    budget: float
    # Extended metrics
    entered_all: int = 0
    interview_reached: int = 0
    offer_received: int = 0
    completed_mtt: int = 0
    completed_spin: int = 0
    completed_cash: int = 0
    contract_mtt: int = 0
    contract_spin: int = 0
    contract_cash: int = 0


class RoistatWeeklyReportResponse(BaseModel):
    rows: List[RoistatWeeklyRow]


class RoistatLessonColumn(BaseModel):
    key: str
    label: str
    module: Optional[int] = None
    lesson: Optional[int] = None


class RoistatLessonUserRow(BaseModel):
    tg_user_id: Optional[int] = None
    username: Optional[str] = None
    pokerhub_user_id: Optional[str] = None
    completed_lessons: int
    lessons: Dict[str, Optional[str]]


class RoistatLessonCourse(BaseModel):
    course: str
    total_lessons: int
    columns: List[RoistatLessonColumn]
    rows: List[RoistatLessonUserRow]


class RoistatLessonsReportResponse(BaseModel):
    courses: List[RoistatLessonCourse]
