from typing import Dict, List

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
    platform: int
    learning: int
    mtt: int
    spin: int
    cash: int
    not_started: int
    channel_subscribed: int
    saloon: int
    completed_course: int
    distance_grinding: int
    contract_signed: int
    budget: float


class RoistatWeeklyReportResponse(BaseModel):
    rows: List[RoistatWeeklyRow]
