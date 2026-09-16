"""Compatibility name for the single Mission Control pipeline."""
from ced_one.mission_control.service import MissionControlService


class MissionControlOrchestrator(MissionControlService):
    """Use MissionControlService for new integrations."""


__all__ = ["MissionControlOrchestrator"]
