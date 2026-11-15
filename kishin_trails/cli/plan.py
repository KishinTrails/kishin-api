"""
``kishin plan`` — training plans, imported from a local JSON file.

    kishin plan import plan.json --start 2026-11-16
    kishin plan list
    kishin plan show
    kishin plan show 3
    kishin plan delete 3 --yes

The file format is described in ``kishin_trails/plan_file.py``. Plans are
personal data: keep the file outside the repositories.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import select

from kishin_trails.database import Base
from kishin_trails.plan_file import PlanFileError, readPlanFile
from kishin_trails.training import ACTIVE_PLAN_ID, ActivePlan, Plan
from kishin_trails.training_types import TICK_TYPES

from .common import fail, openSession

app = typer.Typer(help="Training plans.", no_args_is_help=True)


@app.callback()
def createTables() -> None:
    """Training plans.

    Every command first creates the tables that are missing, as the server does
    at startup, so a database created before the plan tables existed works.
    """
    with openSession() as session:
        Base.metadata.create_all(bind=session.get_bind())


@app.command("import")
def importPlan(
    file: Annotated[Path, typer.Argument(help="Plan file (JSON)", exists=True, dir_okay=False)],
    start: Annotated[datetime.datetime, typer.Option("--start", formats=["%Y-%m-%d"], help="Monday of week 1")],
) -> None:
    """Import a plan and make it the active plan."""
    startDate = start.date()
    if startDate.weekday() != 0:
        fail(f"{startDate} is not a Monday.")

    with openSession() as session:
        try:
            plan = readPlanFile(file)
        except PlanFileError as error:
            for problem in error.problems:
                typer.secho(f"[ERROR] {problem}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from error

        session.add(plan)
        session.flush()
        active = session.get(ActivePlan, ACTIVE_PLAN_ID)
        if active is None:
            session.add(ActivePlan(id=ACTIVE_PLAN_ID, plan_id=plan.id, start_date=startDate))
        else:
            active.plan_id = plan.id
            active.start_date = startDate
        session.commit()
        typer.secho(
            f"[OK] Plan {plan.id} ({plan.name!r}, {len(plan.weeks)} weeks) is the active plan, starting {startDate}.",
            fg=typer.colors.GREEN,
        )


@app.command("list")
def listPlans() -> None:
    """List the plans; * marks the active plan."""
    with openSession() as session:
        activeIds = set(session.scalars(select(ActivePlan.plan_id)))
        plans = session.scalars(select(Plan).order_by(Plan.id)).all()
        if not plans:
            typer.echo("No plans.")
            return
        for plan in plans:
            done = sum(1 for training in plan.trainings if training.completion is not None)
            marker = "*" if plan.id in activeIds else " "
            typer.echo(
                f"{marker} {plan.id:>3}  {plan.name}  ({len(plan.weeks)} weeks, {done}/{len(plan.trainings)} done)"
            )


@app.command("show")
def showPlan(
    planId: Annotated[int | None, typer.Argument(help="Plan id; default: the active plan")] = None,
) -> None:
    """Show a plan's weeks, targets and completions."""
    with openSession() as session:
        if planId is None:
            current = session.get(ActivePlan, ACTIVE_PLAN_ID)
            if current is None:
                fail("Give a plan id: there is no active plan.")
                raise typer.Exit(code=1)
            plan = current.plan
            start: datetime.date | None = current.start_date
        else:
            plan = session.get(Plan, planId)
            if plan is None:
                fail(f"No plan {planId}.")
                raise typer.Exit(code=1)
            active = session.scalar(select(ActivePlan).where(ActivePlan.plan_id == plan.id))
            start = active.start_date if active else None

        typer.echo(f"{plan.name} ({len(plan.weeks)} weeks)" + (f", from {start}" if start else ""))
        for week in plan.weeks:
            monday = f"  {start + datetime.timedelta(weeks=week.week_number - 1)}" if start else ""
            typer.echo(f"\nweek {week.week_number}  {week.phase.value}{monday}")
            for training in plan.trainings:
                if training.week_number != week.week_number:
                    continue
                target = ""
                if training.training_type not in TICK_TYPES:
                    if training.total_distance_km:
                        target = f" {training.total_distance_km:g} km"
                    if training.total_duration_sec:
                        target += f" {training.total_duration_sec // 60} min"
                done = "x" if training.completion else " "
                rpe = f" rpe {training.completion.rpe}" if training.completion and training.completion.rpe else ""
                typer.echo(f"  [{done}] {training.position}. {training.training_type.value}{target}{rpe}")


@app.command("delete")
def deletePlan(
    planId: Annotated[int, typer.Argument(help="Plan id")],
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation")] = False,
) -> None:
    """Delete a plan with its completions; when it is the active plan, there is no active plan afterwards."""
    with openSession() as session:
        plan = session.get(Plan, planId)
        if plan is None:
            fail(f"No plan {planId}.")
            raise typer.Exit(code=1)
        if not yes:
            typer.confirm(f"Delete plan {plan.id} ({plan.name!r}) and its completions?", abort=True)
        for active in session.scalars(select(ActivePlan).where(ActivePlan.plan_id == plan.id)):
            session.delete(active)
        session.delete(plan)
        session.commit()
        typer.secho(f"[OK] Plan {planId} deleted.", fg=typer.colors.GREEN)
