"""Workflow CRUD + immutable versioning.

The graph lives only in `workflow_versions`. Creating a workflow writes v1;
editing writes a new version row and bumps `workflows.current_version`. In-flight
runs keep referencing the version they started on.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Workflow, WorkflowVersion


class WorkflowRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, name: str, graph: dict, description: str | None = None,
        template_id: str | None = None,
    ) -> Workflow:
        workflow = Workflow(
            name=name, description=description, template_id=template_id, current_version=1
        )
        self.session.add(workflow)
        await self.session.flush()
        self.session.add(
            WorkflowVersion(workflow_id=workflow.id, version=1, graph=graph)
        )
        await self.session.flush()
        return workflow

    async def get(self, workflow_id: uuid.UUID) -> Workflow | None:
        return await self.session.get(Workflow, workflow_id)

    async def list(self) -> Sequence[Workflow]:
        result = await self.session.execute(select(Workflow).order_by(Workflow.created_at))
        return result.scalars().all()

    async def get_version(self, workflow_id: uuid.UUID, version: int) -> WorkflowVersion | None:
        return await self.session.get(WorkflowVersion, (workflow_id, version))

    async def get_current_graph(self, workflow_id: uuid.UUID) -> dict | None:
        workflow = await self.get(workflow_id)
        if workflow is None:
            return None
        version = await self.get_version(workflow_id, workflow.current_version)
        return version.graph if version else None

    async def delete(self, workflow_id: uuid.UUID) -> bool:
        """Delete a workflow, its versions (cascade), and its runs."""
        from sqlalchemy import delete as sa_delete

        from app.db.models import Run

        wf = await self.get(workflow_id)
        if wf is None:
            return False
        await self.session.execute(sa_delete(Run).where(Run.workflow_id == workflow_id))
        await self.session.delete(wf)
        await self.session.flush()
        return True

    async def new_version(self, workflow_id: uuid.UUID, graph: dict) -> WorkflowVersion | None:
        """Append an immutable version and advance the pointer."""
        workflow = await self.get(workflow_id)
        if workflow is None:
            return None
        next_version = workflow.current_version + 1
        version = WorkflowVersion(workflow_id=workflow_id, version=next_version, graph=graph)
        self.session.add(version)
        workflow.current_version = next_version
        await self.session.flush()
        return version
