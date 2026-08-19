"""Read-only views over the dr-platform ledger, shaped for the CLI."""

from __future__ import annotations

from dataclasses import dataclass

from dr_platform import (
    CampaignSummary,
    RunMemberSummary,
    StageExecutionState,
    TerminalSummaryFilter,
    StageExecutionSummary,
    WorkItemSummary,
    campaign_state_counts,
    get_work_item_stages,
    list_campaigns,
    list_run_members,
    list_runs,
    list_work_items,
    run_state_counts,
)
from sqlalchemy import Engine

from dr_exp.config.job import ConfigError


@dataclass(frozen=True, slots=True)
class CampaignOverview:
    """One campaign with its per-state work counts."""

    summary: CampaignSummary
    state_counts: dict[str, int]


def overview(
    engine: Engine, *, campaign_key: str | None = None
) -> tuple[CampaignOverview, ...]:
    """Summarize every campaign, or one named campaign."""
    campaigns = list_campaigns(engine=engine)
    if campaign_key is not None:
        campaigns = tuple(
            campaign
            for campaign in campaigns
            if campaign.campaign_key.value == campaign_key
        )
    return tuple(
        CampaignOverview(
            summary=campaign,
            state_counts={
                count.state.value: count.count
                for count in campaign_state_counts(campaign.campaign_key, engine=engine)
            },
        )
        for campaign in campaigns
    )


def run_overview(engine: Engine, *, run_key: str) -> dict[str, int]:
    """Per-state work counts for one run."""
    return {
        count.state.value: count.count
        for count in run_state_counts(run_key, engine=engine)
    }


def run_members(engine: Engine, *, run_key: str) -> tuple[RunMemberSummary, ...]:
    """Every member of one run with its current state."""
    return list_run_members(run_key, engine=engine)


def failed_run_members(engine: Engine, *, run_key: str) -> tuple[RunMemberSummary, ...]:
    """Failed members of one run, with their terminal summary and evidence.

    dr-platform populates ``terminal_summary`` and ``evidence_reference`` only
    on the filtered inspection path, so a diagnosis needs this call rather
    than :func:`run_members`.
    """
    return list_run_members(
        run_key,
        engine=engine,
        terminal_filter=TerminalSummaryFilter(state=StageExecutionState.FAILED),
    )


def campaign_runs(engine: Engine, *, campaign_key: str) -> tuple[str, ...]:
    """The run keys of one campaign, oldest first."""
    return tuple(run.run_key.value for run in list_runs(campaign_key, engine=engine))


def work_items(engine: Engine, *, campaign_key: str) -> tuple[WorkItemSummary, ...]:
    """Every work item of one campaign."""
    return list_work_items(campaign_key, engine=engine)


def resolve_work_item(
    engine: Engine, *, campaign_key: str, work_key: str
) -> WorkItemSummary:
    """Find one work item by exact or unique prefix match on its work key."""
    items = list_work_items(campaign_key, engine=engine)
    exact = [item for item in items if item.work_key.value == work_key]
    if exact:
        return exact[0]
    matches = [item for item in items if item.work_key.value.startswith(work_key)]
    if not matches:
        raise ConfigError(
            f"no work item in campaign {campaign_key!r} matches {work_key!r}"
        )
    if len(matches) > 1:
        listed = ", ".join(sorted(item.work_key.value for item in matches))
        raise ConfigError(
            f"work key {work_key!r} is ambiguous in campaign {campaign_key!r}: {listed}"
        )
    return matches[0]


def work_item_stages(
    engine: Engine, *, work_item_id: int
) -> tuple[StageExecutionSummary, ...]:
    """Every stage execution of one work item, with its attempts."""
    return get_work_item_stages(work_item_id, engine=engine)


__all__ = [
    "CampaignOverview",
    "campaign_runs",
    "failed_run_members",
    "overview",
    "resolve_work_item",
    "run_members",
    "run_overview",
    "work_item_stages",
    "work_items",
]
