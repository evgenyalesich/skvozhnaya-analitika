from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from fastapi import HTTPException, Query

MAX_DATE_RANGE_DAYS = 730


@dataclass
class ReportFilters:
    start_date: Optional[date]
    end_date: Optional[date]
    bots: List[str]
    advertising_companies: List[str]
    utm_source: List[str]
    utm_campaign: List[str]
    utm_medium: List[str]
    utm_content: List[str]
    utm_term: List[str]
    user_scope: Optional[str] = None

    def has_filters(self) -> bool:
        return any(
            [
                self.start_date is not None,
                self.end_date is not None,
                bool(self.bots),
                bool(self.advertising_companies),
                bool(self.utm_source),
                bool(self.utm_campaign),
                bool(self.utm_medium),
                bool(self.utm_content),
                bool(self.utm_term),
                bool(self.user_scope and self.user_scope != "all"),
            ]
        )


@dataclass
class RawReportParams:
    limit: int
    offset: int
    sort_by: str
    sort_direction: str


@dataclass
class RawUserFilters:
    bot_keys: List[str]
    tg_user_id: Optional[str]
    utm_source: List[str]
    utm_campaign: List[str]
    utm_medium: List[str]
    utm_content: List[str]
    utm_term: List[str]
    advertising_companies: List[str]
    budget_min: Optional[float]
    budget_max: Optional[float]
    converted_to_lead: Optional[bool]
    registered_platform: Optional[bool]
    started_learning: Optional[bool]
    completed_course: Optional[bool]
    used_simulator: Optional[bool]
    interview_reached: Optional[bool]
    interview_passed: Optional[bool]
    offer_received: Optional[bool]
    contract_signed: Optional[bool]
    distance_grinding: Optional[bool]
    interview_reached_status: Optional[str]
    interview_passed_status: Optional[str]
    offer_received_status: Optional[str]
    contract_signed_status: Optional[str]
    channel_subscribed: Optional[bool]
    community_member: Optional[bool]
    team_member: Optional[bool]
    community_member_status: Optional[str]
    internal_status: Optional[str]
    user_block: Optional[bool]
    user_status: Optional[str]
    first_touch_present: Optional[bool]
    last_touch_present: Optional[bool]
    source_categories: List[str]


def get_report_filters(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    bots: Optional[List[str]] = Query(None),
    advertising_companies: Optional[List[str]] = Query(None),
    utm_source: Optional[List[str]] = Query(None),
    utm_campaign: Optional[List[str]] = Query(None),
    utm_medium: Optional[List[str]] = Query(None),
    utm_content: Optional[List[str]] = Query(None),
    utm_term: Optional[List[str]] = Query(None),
    user_scope: Optional[str] = Query(None),
) -> ReportFilters:
    if start_date and end_date:
        if end_date < start_date:
            raise HTTPException(status_code=400, detail="end_date must be after start_date")
        if (end_date - start_date).days > MAX_DATE_RANGE_DAYS:
            raise HTTPException(
                status_code=400,
                detail=f"Date range must not exceed {MAX_DATE_RANGE_DAYS} days",
            )
    return ReportFilters(
        start_date=start_date,
        end_date=end_date,
        bots=bots or [],
        advertising_companies=advertising_companies or [],
        utm_source=utm_source or [],
        utm_campaign=utm_campaign or [],
        utm_medium=utm_medium or [],
        utm_content=utm_content or [],
        utm_term=utm_term or [],
        user_scope=user_scope,
    )


ALLOWED_SORT_FIELDS = {
    "created_at": "created_at",
    "tg_user_id": "tg_user_id",
    "bot_key": "bot_key",
    "budget": "budget",
    "utm_source": "utm_source",
    "utm_campaign": "utm_campaign",
    "utm_medium": "utm_medium",
    "utm_content": "utm_content",
    "utm_term": "utm_term",
    "advertising_company": "advertising_company",
    "ingested_at": "ingested_at",
}


def get_raw_report_params(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at"),
    sort_direction: str = Query("desc", pattern="^(asc|desc)$"),
) -> RawReportParams:
    if sort_by not in ALLOWED_SORT_FIELDS:
        raise HTTPException(status_code=400, detail=f"sort_by must be one of {sorted(ALLOWED_SORT_FIELDS)}")
    return RawReportParams(limit=limit, offset=offset, sort_by=sort_by, sort_direction=sort_direction)


def get_raw_user_filters(
    raw_bot_key: Optional[List[str]] = Query(None),
    raw_tg_user_id: Optional[str] = Query(None),
    raw_utm_source: Optional[List[str]] = Query(None),
    raw_utm_campaign: Optional[List[str]] = Query(None),
    raw_utm_medium: Optional[List[str]] = Query(None),
    raw_utm_content: Optional[List[str]] = Query(None),
    raw_utm_term: Optional[List[str]] = Query(None),
    raw_advertising_company: Optional[List[str]] = Query(None),
    raw_budget_min: Optional[float] = Query(None),
    raw_budget_max: Optional[float] = Query(None),
    raw_converted_to_lead: Optional[bool] = Query(None),
    raw_registered_platform: Optional[bool] = Query(None),
    raw_started_learning: Optional[bool] = Query(None),
    raw_completed_course: Optional[bool] = Query(None),
    raw_used_simulator: Optional[bool] = Query(None),
    raw_interview_reached: Optional[bool] = Query(None),
    raw_interview_passed: Optional[bool] = Query(None),
    raw_offer_received: Optional[bool] = Query(None),
    raw_contract_signed: Optional[bool] = Query(None),
    raw_distance_grinding: Optional[bool] = Query(None),
    raw_interview_reached_status: Optional[str] = Query(None),
    raw_interview_passed_status: Optional[str] = Query(None),
    raw_offer_received_status: Optional[str] = Query(None),
    raw_contract_signed_status: Optional[str] = Query(None),
    raw_channel_subscribed: Optional[bool] = Query(None),
    raw_community_member: Optional[bool] = Query(None),
    raw_team_member: Optional[bool] = Query(None),
    raw_community_member_status: Optional[str] = Query(None),
    raw_internal_status: Optional[str] = Query(None),
    raw_user_block: Optional[bool] = Query(None),
    raw_user_status: Optional[str] = Query(None),
    raw_first_touch_present: Optional[bool] = Query(None),
    raw_last_touch_present: Optional[bool] = Query(None),
    raw_source_category: Optional[List[str]] = Query(None),
) -> RawUserFilters:
    return RawUserFilters(
        bot_keys=raw_bot_key or [],
        tg_user_id=raw_tg_user_id,
        utm_source=raw_utm_source or [],
        utm_campaign=raw_utm_campaign or [],
        utm_medium=raw_utm_medium or [],
        utm_content=raw_utm_content or [],
        utm_term=raw_utm_term or [],
        advertising_companies=raw_advertising_company or [],
        budget_min=raw_budget_min,
        budget_max=raw_budget_max,
        converted_to_lead=raw_converted_to_lead,
        registered_platform=raw_registered_platform,
        started_learning=raw_started_learning,
        completed_course=raw_completed_course,
        used_simulator=raw_used_simulator,
        interview_reached=raw_interview_reached,
        interview_passed=raw_interview_passed,
        offer_received=raw_offer_received,
        contract_signed=raw_contract_signed,
        distance_grinding=raw_distance_grinding,
        interview_reached_status=raw_interview_reached_status,
        interview_passed_status=raw_interview_passed_status,
        offer_received_status=raw_offer_received_status,
        contract_signed_status=raw_contract_signed_status,
        channel_subscribed=raw_channel_subscribed,
        community_member=raw_community_member,
        team_member=raw_team_member,
        community_member_status=raw_community_member_status,
        internal_status=raw_internal_status,
        user_block=raw_user_block,
        user_status=raw_user_status,
        first_touch_present=raw_first_touch_present,
        last_touch_present=raw_last_touch_present,
        source_categories=raw_source_category or [],
    )
